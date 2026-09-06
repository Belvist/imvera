"""Speech segment collector with pre-roll."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass
class EndpointConfig:
    pre_roll_ms: int = 250
    frame_ms: int = 20


class SpeechSegmentCollector:
    def __init__(self, sample_rate: int, config: EndpointConfig | None = None) -> None:
        self.sample_rate = sample_rate
        self.config = config or EndpointConfig()
        frames = max(1, self.config.pre_roll_ms // self.config.frame_ms)
        self._pre_roll: deque[bytes] = deque(maxlen=frames)
        self._segment: list[bytes] = []
        self._collecting = False

    def on_frame(self, pcm: bytes, speech_started: bool, speech_ended: bool) -> bytes | None:
        if not self._collecting:
            self._pre_roll.append(pcm)
            if speech_started:
                self._collecting = True
                self._segment = list(self._pre_roll)
                self._segment.append(pcm)
            return None
        self._segment.append(pcm)
        if speech_ended:
            self._collecting = False
            out = b"".join(self._segment)
            self._segment = []
            return out
        return None
