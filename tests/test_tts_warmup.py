"""TTS startup warmup helper."""

from __future__ import annotations

import queue

from services.tts.warmup import warmup_synthesis
from services.tts.worker import SynthesizeRequest


def test_warmup_synthesis_sync_first_pcm() -> None:
    def produce(req: SynthesizeRequest, out_q: queue.Queue) -> None:
        out_q.put(
            {
                "sequence": 0,
                "sample_rate": 24000,
                "pcm_b64": "AAA=",
                "is_last": False,
            }
        )
        out_q.put(None)

    elapsed = warmup_synthesis(produce, text="А.")
    assert elapsed >= 0.0


def test_warmup_synthesis_no_audio_returns_zero() -> None:
    def produce(_req: SynthesizeRequest, out_q: queue.Queue) -> None:
        out_q.put(None)

    assert warmup_synthesis(produce) == 0.0
