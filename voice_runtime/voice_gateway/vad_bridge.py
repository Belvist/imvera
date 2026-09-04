"""Silero VAD bridge for voice gateway PCM streams."""
from __future__ import annotations

from typing import Iterable, List

try:
    from voice_runtime.vad import VAD, MIN_TURN_SAMPLES, SAMPLE_RATE
except ImportError:
    from vad import VAD, MIN_TURN_SAMPLES, SAMPLE_RATE

VAD_STEP = int(SAMPLE_RATE * 0.03)


class GatewayVadBridge:
    """Feeds 16 kHz mono PCM int16 chunks into the shared VAD."""

    def __init__(self) -> None:
        self._vad = VAD()

    @property
    def sample_rate(self) -> int:
        return SAMPLE_RATE

    def feed_pcm(self, samples: Iterable[int], *, agent_speaking: bool = False):
        buf: List[int] = list(samples)
        events = []
        for i in range(0, len(buf), VAD_STEP):
            chunk = buf[i:i + VAD_STEP]
            if not chunk:
                continue
            ms = 1000.0 * len(chunk) / SAMPLE_RATE
            turn, onset = self._vad.feed(
                chunk,
                ms,
                agent_speaking=agent_speaking,
            )
            if onset:
                events.append({"type": "speech_onset"})
            if turn and len(turn) >= MIN_TURN_SAMPLES:
                events.append({"type": "turn_complete", "samples": turn})
        return events
