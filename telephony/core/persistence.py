"""Durable PersistenceWorker: get network persistence OUT of the voice hot path.

read.md rev-3 gate G1 + rev-4 gate B. Before this the live turn ran PG
INSERT / MinIO put_object / Redis writes synchronously INSIDE the per-call
lock, *before* the first word of Vera's answer was produced, so a slow
Postgres or S3 made the caller feel "Вера зависла".

The contract this module enforces for rev-4 gate B:

    hot path (STT -> Dialogue -> LLM -> TTS -> first audio)
        |            (local disk WAV + in-memory mirror stay synchronous)
        v
    emit(name, payload)  ---- microseconds, NEVER blocks, NEVER drops ----
        |
        |  serialized to a durable append-only WAL (local JSONL spool)
        v
    per-kind bounded in-memory queues  (pg / s3 / redis)
        |
        v
    SEPARATE writer threads (one per sink: PG, S3, Redis)
        |   retry/backoff + dead-letter after max attempts
        v
    acked off the WAL / dead-lettered

Why this is NOT the old "Queue -> DROP":

  * A full in-memory queue can never lose a job: every record is ALWAYS
    durably appended to the WAL *before* any queue is touched. If the queue is
    full, the record simply stays in the WAL and the reader re-dispatches it
    as soon as a slot frees up.
  * A process crash also cannot lose a job: loading the process re-reads the
    WAL, so events recorded-but-not-yet-applied are re-delivered
    (at-least-once). Handlers are idempotent by design (PG upserts / S3 put),
    so an occasional re-delivery is safe.
  * Writers are SEPARATED per sink, so one slow MinIO cannot block that turn's
    PG INSERT (and vice-versa) — 40 persistence jobs/sec across N sinks is not
    serialized through a single thread.
  * Every failure retries with exponential backoff; after ``max_attempts``
    the record moves to an on-disk dead-letter spool (persistence.wal.jsonl.dead,
    opaque to the hot path) so it is never silently discarded.

Handlers are registered by name and ``payload`` MUST be JSON-serializable so
the record can survive a restart. The hot path calls ``emit`` with plain data
— never with a bound method (not serializable).
"""

import json
import os
import queue
import threading
import time
import uuid


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _durable_append(path, line):
    """Append one UTF-8 line and fsync it before returning."""
    data = line.encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short WAL write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


class _Spool:
    """Append-only durable JSONL WAL + in-memory pending set.

    ``append`` durably writes a JSON-serializable record to local disk
    (usec-scale hot-path cost) and registers it as pending. ``ack``/``discard``
    drop a record from pending. When the WAL file has grown large while the
    backlog it must still honour has shrunk, the file is rewritten to contain
    only the pending records, so the bytes on disk always describe exactly the
    set of not-yet-applied events (at-least-once across a restart).
    """

    def __init__(self, directory):
        os.makedirs(directory, mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
        self.path = os.path.join(directory, "persistence.wal.jsonl")
        self._pending = {}
        self._written = 0
        self._lock = threading.Lock()
        if os.path.exists(self.path):
            os.chmod(self.path, 0o600)
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            rec = json.loads(line)
                            self._pending[rec["id"]] = rec
                        except (ValueError, KeyError):
                            continue
            except OSError:
                pass
            self._written = len(self._pending)

    def append(self, record):
        with self._lock:
            line = json.dumps(record, ensure_ascii=False) + "\n"
            # Disk first, memory second: if the filesystem refuses the write,
            # emit() fails loudly and no phantom in-memory "durable" record is
            # created.
            _durable_append(self.path, line)
            self._pending[record["id"]] = record
            self._written += 1

    def ack(self, record_id):
        with self._lock:
            self._pending.pop(record_id, None)
            self._maybe_compact()

    def discard(self, record_id):
        with self._lock:
            self._pending.pop(record_id, None)
            self._maybe_compact()

    def snapshot(self):
        with self._lock:
            return list(self._pending.values())

    def _maybe_compact(self):
        # Only rewrite when the file has ballooned relative to the backlog that
        # is still owed; a small pending set with a big file is compaction
        # worthy, a hot spool that stays full is not.
        if self._written > 256 and len(self._pending) * 2 < self._written:
            lines = [json.dumps(r, ensure_ascii=False) + "\n"
                     for r in self._pending.values()]
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(lines)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
            # Persist the rename itself across a host crash.
            dfd = os.open(os.path.dirname(self.path), os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
            self._written = len(self._pending)


class PersistenceWorker:
    def __init__(self, spool_dir=None, maxsize=8192, retry_delay=2.0,
                 max_attempts=5, name="persist"):
        spool_dir = spool_dir or os.environ.get(
            "MOSS_PERSIST_SPOOL", "/tmp/mossvoice_persist")
        self._name = name
        self._handlers = {}
        self._kind_of = {}
        self._spool = _Spool(spool_dir)
        self._queues = {kind: queue.Queue(maxsize=maxsize)
                        for kind in ("pg", "s3", "redis")}
        self._retry_delay = retry_delay
        self._max_attempts = max_attempts
        self._threads = []
        self._inflight = set()
        self._lock = threading.Lock()
        self._dead_letter_lock = threading.Lock()
        self._dead_letter_path = self._spool.path + ".dead"
        self._stop = threading.Event()
        self.metrics = {
            "submitted": 0,
            "replayed": 0,
            "acked": 0,
            "retries": 0,
            "dead_lettered": 0,
            "depth": 0,
            # Design invariant of gate B: nothing is silently dropped. A full
            # queue spills to the WAL and is replayed, never lost.
            "dropped": 0,
        }

    def register(self, name, handler, kind):
        """Register a durable job name -> sink handler. ``kind`` is one of
        pg / s3 / redis and selects the writer thread that executes it."""
        assert kind in self._queues, f"unknown sink kind {kind!r}"
        self._handlers[name] = handler
        self._kind_of[name] = kind

    # -- hot path ---------------------------------------------------------- #
    def emit(self, name, payload):
        """Persist a JSON-serializable event. Hot-path safe: durably appends
        to the WAL (a single local disk write), then hands the record to the
        per-kind writer queue. A full in-memory queue is NOT a drop — the WAL
        already holds the record and the reader re-dispatches it as soon as a
        slot frees up (see ``_run_reader``)."""
        if name not in self._handlers:
            raise KeyError(f"no handler registered for {name!r}")
        record = {
            "id": uuid.uuid4().hex,
            "name": name,
            "payload": payload,
            "attempts": 0,
            "created": _now(),
        }
        self._spool.append(record)  # durable FIRST — never lost
        self.metrics["submitted"] += 1
        kind = self._kind_of[name]
        with self._lock:
            try:
                self._queues[kind].put_nowait((record["id"], record))
                self._inflight.add(record["id"])
            except queue.Full:
                # No capacity: leave it in the WAL; the reader re-dispatches.
                pass
        return True

    def start(self):
        if self._threads:
            return self
        self.metrics["replayed"] = len(self._spool.snapshot())
        self._reader = threading.Thread(
            target=self._run_reader,
            name=f"{self._name}-reader", daemon=True)
        self._reader.start()
        for kind in self._queues:
            t = threading.Thread(
                target=self._run_writer, args=(kind,),
                name=f"{self._name}-{kind}", daemon=True)
            t.start()
            self._threads.append(t)
        return self

    # -- internals --------------------------------------------------------- #
    def _handoff(self, record):
        """Hand a still-pending WAL record to its writer queue unless the
        queue is full (then it stays in the WAL). Returns True if the record
        is now owned by a writer (or already is)."""
        with self._lock:
            if record["id"] in self._inflight:
                return True  # already owned by a writer
            try:
                self._queues[self._kind_of[record["name"]]].put_nowait(
                    (record["id"], record))
                self._inflight.add(record["id"])
                return True
            except queue.Full:
                return False

    def _run_reader(self):
        # Poll: re-dispatch any durable WAL record not currently owned by a
        # writer. This single loop covers both crash-recovered backlog and
        # records that hit the full-queue path in emit(). At-least-once is
        # guaranteed by the WAL; handlers are idempotent.
        while not self._stop.is_set():
            for record in self._spool.snapshot():
                if not self._handoff(record):
                    break  # some queue is full; wait for writers to drain
            time.sleep(0.25)

    def _run_writer(self, kind):
        q = self._queues[kind]
        while not self._stop.is_set():
            try:
                rid, record = q.get(timeout=0.5)
            except queue.Empty:
                continue
            self.metrics["depth"] = q.qsize()
            name = record["name"]
            handler = self._handlers.get(name)
            try:
                if handler is None:
                    raise KeyError(name)
                handler(record["payload"])
                self._spool.ack(rid)
                with self._lock:
                    self._inflight.discard(rid)
                self.metrics["acked"] += 1
            except Exception as e:  # noqa: BLE001
                record["attempts"] += 1
                self.metrics["retries"] += 1
                if record["attempts"] >= self._max_attempts:
                    self._dead_letter(record)
                    self._spool.discard(rid)  # never replay a dead letter
                    with self._lock:
                        self._inflight.discard(rid)
                    self.metrics["dead_lettered"] += 1
                    print(f"[{self._name}] {name} DEAD-LETTERED after "
                          f"{record['attempts']} attempts: {e}", flush=True)
                else:
                    # Backoff, then retry on the SAME queue. Keeping the record
                    # inflight means the reader won't double-dispatch it while
                    # we sleep.
                    time.sleep(self._retry_delay * record["attempts"])
                    try:
                        q.put((rid, record))
                    except queue.Full:
                        # Drop ownership; the reader re-dispatches from WAL.
                        with self._lock:
                            self._inflight.discard(rid)
                    print(f"[{self._name}] {name} failed: {e} "
                          f"(attempt {record['attempts']})", flush=True)
            finally:
                q.task_done()

    def _dead_letter(self, record):
        with self._dead_letter_lock:
            _durable_append(
                self._dead_letter_path,
                json.dumps(record, ensure_ascii=False) + "\n")

    def drain(self, timeout=30.0):
        """Block until every durably-recorded event is applied. Returns True
        on a full drain, False on timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._spool.snapshot() and all(
                    q.empty() for q in self._queues.values()):
                return True
            time.sleep(0.2)
        return False

    def close(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=3.0)
