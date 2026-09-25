"""Runtime trace — JSONL per call for voice lab diagnostics.

Hot-path safe (P0 plan 3b): record_event() only enqueues (<10us) and a
single daemon thread does the file I/O. flush_traces() drains the queue
(call finalize path). Dropped-event counter on overflow instead of OOM.
IMVERA_TRACE_SYNC=1 restores direct writes (debug only).
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from packages.contracts.runtime import RuntimeEvent

ROOT = Path(__file__).resolve().parents[2]
TRACE_DIR = ROOT / ".run" / "traces"

_MAX_QUEUE = 20000

_log = logging.getLogger("voice.trace")

_queue: queue.Queue = queue.Queue(maxsize=_MAX_QUEUE)
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()
dropped_events = 0


def _write_row(call_id: str, row: dict) -> None:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / f"{call_id}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _worker_loop() -> None:
    while True:
        item = _queue.get()
        if item is None:
            _queue.task_done()
            return
        call_id, row = item
        try:
            _write_row(call_id, row)
        except Exception:
            _log.exception("trace write failed call_id=%s", call_id)
        finally:
            _queue.task_done()


def _ensure_worker() -> None:
    global _worker
    if _worker is not None and _worker.is_alive():
        return
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(
            target=_worker_loop, name="trace-writer", daemon=True
        )
        _worker.start()


def _sync_enabled() -> bool:
    return os.environ.get("IMVERA_TRACE_SYNC") == "1"


def record_event(call_id: str, event: RuntimeEvent) -> None:
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "call_id": call_id,
        "type": event.event_type.value,
        "payload": event.payload,
    }
    if _sync_enabled():
        _write_row(call_id, row)
        return
    _ensure_worker()
    global dropped_events
    try:
        _queue.put_nowait((call_id, row))
    except queue.Full:
        dropped_events += 1
        if dropped_events % 100 == 1:
            _log.warning("trace queue full, dropped %d events", dropped_events)


def flush_traces(timeout_s: float = 10.0) -> bool:
    """Drain pending writes. Returns True when fully drained."""
    _ensure_worker()
    deadline = time.monotonic() + timeout_s
    while _queue.unfinished_tasks > 0:
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.005)
    return True


def trace_path(call_id: str) -> Path:
    return TRACE_DIR / f"{call_id}.jsonl"


def _flush_at_exit() -> None:
    try:
        flush_traces(timeout_s=5.0)
    except Exception:
        pass


atexit.register(_flush_at_exit)
