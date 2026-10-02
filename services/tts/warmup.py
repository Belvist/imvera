"""TTS synthesis warmup — first generate() after load_model can take 10–30s."""

from __future__ import annotations

import queue
import threading
import time
import uuid
from collections.abc import Callable

from services.tts.worker import SynthesizeRequest


class _WarmupQueue(queue.Queue):
    """Stop a timed-out producer waiting on a full bounded PCM queue."""

    def __init__(self, cancelled: threading.Event) -> None:
        super().__init__(maxsize=8)
        self._cancelled = cancelled

    def put(self, item, block=True, timeout=None) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be non-negative")
        while True:
            if self._cancelled.is_set():
                raise TimeoutError("TTS warmup queue cancelled")
            if not block:
                return super().put(item, block=False)
            remaining = None if deadline is None else deadline - time.monotonic()
            try:
                return super().put(
                    item, timeout=0.05 if remaining is None else max(0, min(0.05, remaining))
                )
            except queue.Full:
                if deadline is not None and time.monotonic() >= deadline:
                    raise


def warmup_synthesis(
    produce_fn: Callable[[SynthesizeRequest, queue.Queue], None],
    *,
    text: str = "Здравствуйте.",
    timeout_s: float = 120.0,
) -> float:
    """Complete one short synthesis, then return seconds until its first PCM.

    The producer runs on a thread while the caller drains: a bounded
    queue with a synchronous producer deadlocks once it fills (live:
    qwen warmup parked forever on put #9). Same shape as the live
    ndjson streamer.
    """
    cancelled = threading.Event()
    completed = threading.Event()
    errors: list[BaseException] = []
    out_q = _WarmupQueue(cancelled)
    req = SynthesizeRequest(
        call_id="warmup",
        generation_id=f"warm-{uuid.uuid4().hex[:8]}",
        phrase_id="warm-p",
        text=text,
    )
    started = time.monotonic()
    first_s: float | None = None

    def produce() -> None:
        try:
            produce_fn(req, out_q)
        except BaseException as exc:
            errors.append(exc)
        finally:
            completed.set()

    producer = threading.Thread(target=produce, daemon=True)
    producer.start()
    deadline = started + timeout_s
    while True:
        if completed.is_set() and out_q.empty():
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            cancelled.set()
            producer.join(timeout=0.1)
            raise TimeoutError(f"TTS warmup did not complete within {timeout_s:g}s")
        try:
            item = out_q.get(timeout=min(0.05, remaining))
        except queue.Empty:
            continue
        if item is None:
            # A producer can raise after writing its sentinel in finally.
            continue
        if item.get("error"):
            errors.append(RuntimeError(str(item["error"])))
        if first_s is None and item.get("pcm_b64"):
            first_s = time.monotonic() - started
    producer.join()
    if errors:
        raise errors[0]
    return first_s if first_s is not None else 0.0
