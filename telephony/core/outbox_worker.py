"""Outbox polling worker (Phase 2).

Delivers outbox_messages to downstream channels (Telegram, SMS, ...) with a
lease: a message is claimed via ``FOR UPDATE SKIP LOCKED`` and must resolve
within the lock window, otherwise another worker picks it up. Dispatch is
idempotent at the consumer level (the payload carries the message id / a
dedup key the consumer dedupes on). Failed deliveries retry with backoff and
die after max_attempts.
"""

import os
import threading
import time


class OutboxWorker:
    def __init__(self, pg, dispatch, poll_interval=5.0, lock_seconds=60,
                 max_attempts=10, batch=10, worker_id="",
                 retry_delay_seconds=10, tick=None):
        """``dispatch(topic, payload, msg_id) -> bool``.
        ``tick()`` (optional) runs on every poll cycle — used for incident
        escalation deadlines; must be cheap and exception-safe.
        """
        self.pg = pg
        self.dispatch = dispatch
        self.tick = tick
        self.poll_interval = poll_interval
        self.lock_seconds = lock_seconds
        self.max_attempts = max_attempts
        self.batch = batch
        self.worker_id = worker_id or os.environ.get("MOSS_WORKER_ID", "w1")
        self.retry_delay_seconds = retry_delay_seconds
        self._stop = threading.Event()
        self._thread = None

    # ------------------------------------------------------------------ #
    def run_once(self, limit=None):
        """Claim + deliver one batch. Returns (claimed, delivered)."""
        rows = self.pg.claim_batch(
            limit=limit or self.batch, worker_id=self.worker_id,
            lock_seconds=self.lock_seconds)
        claimed = len(rows or [])
        delivered = 0
        for row in rows:
            try:
                ok = self.dispatch(row["topic"], row["payload"],
                                   row["id"])
            except Exception:  # noqa: BLE001
                ok = False
            self.pg.resolve_outbox(
                row["id"], ok,
                delay_seconds=self.retry_delay_seconds,
                max_attempts=self.max_attempts)
            if ok:
                delivered += 1
        return claimed, delivered

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.poll_interval * 2 + 1)

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as e:  # noqa: BLE001
                print(f"[outbox] cycle error: {e}", flush=True)
            if self.tick is not None:
                try:
                    self.tick()
                except Exception as e:  # noqa: BLE001
                    print(f"[outbox] tick error: {e}", flush=True)
            self._stop.wait(self.poll_interval)