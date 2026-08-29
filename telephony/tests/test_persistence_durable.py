"""rev-4 Gate B — durable PersistenceWorker spool.

Invariants the durable hot path must enforce (read.md rev-4 gate B):
- a FULL in-memory queue is never a drop: the record is already durable in the
  JSONL WAL and the reader re-dispatches it once a slot frees up (``dropped``
  is by design always 0);
- a process restart re-delivers events recorded-but-not-applied (at-least-once
  via the startup replay), handlers are idempotent;
- a permanently-failing sink is retried with backoff and then moved to an
  on-disk dead-letter spool instead of being silently discarded.

Runs fully offline (no Postgres / Redis / MinIO).
"""
import os
import sys
import tempfile
import threading
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from core.persistence import PersistenceWorker, _Spool  # noqa: E402


class PersistenceDurableTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="moss_persist_test_")

    def _spool_dir(self):
        return os.path.join(self._tmpdir, "spool")

    def _wait_until(self, cond, timeout=8.0):
        deadline = threading.Event()
        deadline.wait(0)  # no-op
        t0 = __import__("time").time()
        while __import__("time").time() - t0 < timeout:
            if cond():
                return True
            __import__("time").sleep(0.05)
        return cond()

    def test_full_queue_never_drops_durable_replay(self):
        """All emitted jobs are applied exactly-once-in-effect even with a tiny
        queue; dropped stays 0."""
        seen = []
        p = PersistenceWorker(spool_dir=self._spool_dir(), maxsize=4,
                              retry_delay=0.01, max_attempts=3)
        p.register("job", lambda payload: seen.append(payload["i"]), "pg")
        p.start()
        for i in range(40):
            p.emit("job", {"i": i})
        self.assertTrue(p.drain(timeout=8.0),
                        "durable spool should drain everything")
        self.assertEqual(len(seen), 40, "no job may be lost on a full queue")
        self.assertEqual(sorted(seen), list(range(40)))
        self.assertEqual(p.metrics["acked"], 40)
        self.assertEqual(p.metrics["dropped"], 0,
                         "gate B: a full queue must never drop")
        p.close()

    def test_startup_replay_recovers_unacked_events(self):
        """Recorded-but-unacknowledged events survive a restart (at-least-once)."""
        spool = _Spool(self._spool_dir())
        spool.append({"id": "a", "name": "job", "payload": {"x": 1},
                      "attempts": 0, "created": "t"})
        spool.append({"id": "b", "name": "job", "payload": {"x": 2},
                      "attempts": 0, "created": "t"})
        seen = []
        p = PersistenceWorker(spool_dir=self._spool_dir(), retry_delay=0.01)
        p.register("job", lambda payload: seen.append(payload["x"]), "s3")
        self.assertEqual(p.metrics["replayed"], 0)  # not started yet
        p.start()
        self.assertTrue(p.drain(timeout=8.0))
        self.assertEqual(sorted(seen), [1, 2])
        self.assertEqual(p.metrics["replayed"], 2,
                         "the two pre-existing WAL records must replay")
        p.close()

    def test_persistent_failure_retries_then_dead_letters(self):
        """A permanently failing sink is never silently dropped: it retries
        and then lands in the on-disk dead-letter spool."""
        p = PersistenceWorker(spool_dir=self._spool_dir(),
                              retry_delay=0.01, max_attempts=3)

        def flaky(payload):  # noqa: ARG001
            raise RuntimeError("sink unreachable")

        p.register("bad", flaky, "redis")
        p.start()
        p.emit("bad", {"z": 9})
        self.assertTrue(
            self._wait_until(lambda: p.metrics["dead_lettered"] >= 1),
            "permanent failure should dead-letter after max_attempts")
        self.assertEqual(p.metrics["retries"], 3)
        self.assertEqual(p.metrics["dropped"], 0)
        self.assertTrue(os.path.exists(p._dead_letter_path),
                        "dead-letter spool file should exist")
        with open(p._dead_letter_path, encoding="utf-8") as f:
            lines = [ln for ln in f if ln.strip()]
        self.assertEqual(len(lines), 1)
        rec = __import__("json").loads(lines[0])
        self.assertEqual(rec["name"], "bad")
        self.assertEqual(rec["attempts"], 3)
        p.close()


if __name__ == "__main__":
    unittest.main()
