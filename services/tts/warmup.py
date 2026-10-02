"""TTS synthesis warmup — first generate() after load_model can take 10–30s."""

from __future__ import annotations

import queue
import threading
import time
import uuid
from collections.abc import Callable

from services.tts.worker import SynthesizeRequest


def warmup_synthesis(
    produce_fn: Callable[[SynthesizeRequest, queue.Queue], None],
    *,
    text: str = "Здравствуйте.",
    timeout_s: float = 120.0,
) -> float:
    """Run one short synthesis; return seconds until first PCM.

    The producer runs on a thread while the caller drains: a bounded
    queue with a synchronous producer deadlocks once it fills (live:
    qwen warmup parked forever on put #9). Same shape as the live
    ndjson streamer.
    """
    out_q: queue.Queue = queue.Queue(maxsize=8)
    req = SynthesizeRequest(
        call_id="warmup",
        generation_id=f"warm-{uuid.uuid4().hex[:8]}",
        phrase_id="warm-p",
        text=text,
    )
    started = time.monotonic()
    first_s: float | None = None
    producer = threading.Thread(
        target=produce_fn, args=(req, out_q), daemon=True
    )
    producer.start()
    deadline = started + timeout_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            item = out_q.get(timeout=min(1.0, remaining))
        except queue.Empty:
            continue
        if item is None:
            break
        if first_s is None and item.get("pcm_b64"):
            first_s = time.monotonic() - started
    producer.join(timeout=5.0)
    return first_s if first_s is not None else 0.0
