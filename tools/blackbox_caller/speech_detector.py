"""Local downlink speech/silence detection — caller oracle input only."""

from __future__ import annotations

from dataclasses import dataclass

SILENCE_CENTER = 128


@dataclass
class SpeechDetectorConfig:
    sample_rate: int = 8000
    frame_ms: int = 20
    speech_rms_threshold: float = 12.0
    silence_frames_for_end: int = 45  # ~900 ms @ 20ms


class DownlinkSpeechDetector:
    """Detect bot speaking vs silence from downlink u8 PCM chunks."""

    def __init__(self, config: SpeechDetectorConfig | None = None) -> None:
        self.config = config or SpeechDetectorConfig()
        self._bot_speaking = False
        self._silence_run = 0
        self._speech_run = 0
        self._last_rms = 0.0

    @staticmethod
    def _rms_u8(chunk: bytes) -> float:
        if not chunk:
            return 0.0
        acc = 0.0
        for b in chunk:
            d = float(b - SILENCE_CENTER)
            acc += d * d
        return (acc / len(chunk)) ** 0.5

    def feed(self, chunk: bytes) -> tuple[bool, bool]:
        """Return (bot_speaking, bot_just_finished)."""
        rms = self._rms_u8(chunk)
        self._last_rms = rms
        if rms >= self.config.speech_rms_threshold:
            self._speech_run += 1
            self._silence_run = 0
            self._bot_speaking = True
            return True, False
        if self._bot_speaking:
            self._silence_run += 1
            if self._silence_run >= self.config.silence_frames_for_end:
                self._bot_speaking = False
                self._speech_run = 0
                return False, True
            return True, False
        return False, False

    @property
    def bot_speaking(self) -> bool:
        return self._bot_speaking

    @property
    def last_rms(self) -> float:
        return self._last_rms
