"""Energy-based VAD — calibration baseline until Silero VAD adapter is wired."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VadConfig:
    energy_threshold: float = 500.0
    min_speech_ms: int = 100
    min_silence_ms: int = 650
    frame_ms: int = 20


class EnergyVad:
    """Simple RMS gate for endpointing bootstrap (not production-tuned)."""

    def __init__(self, sample_rate: int, config: VadConfig | None = None) -> None:
        self.sample_rate = sample_rate
        self.config = config or VadConfig()
        self._in_speech = False
        self._speech_ms = 0
        self._silence_ms = 0

    def _rms(self, pcm: bytes) -> float:
        if len(pcm) < 2:
            return 0.0
        import array
        import math

        samples = array.array("h")
        samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
        if not samples:
            return 0.0
        acc = sum(s * s for s in samples)
        return math.sqrt(acc / len(samples))

    def feed(self, pcm: bytes) -> tuple[bool, bool]:
        """Return (speech_started, speech_ended) edge flags for this frame."""
        loud = self._rms(pcm) >= self.config.energy_threshold
        started = False
        ended = False
        if loud:
            self._silence_ms = 0
            self._speech_ms += self.config.frame_ms
            if not self._in_speech and self._speech_ms >= self.config.min_speech_ms:
                self._in_speech = True
                started = True
        else:
            if self._in_speech:
                self._silence_ms += self.config.frame_ms
                if self._silence_ms >= self.config.min_silence_ms:
                    self._in_speech = False
                    self._speech_ms = 0
                    ended = True
            else:
                self._speech_ms = 0
        return started, ended

    @property
    def in_speech(self) -> bool:
        return self._in_speech
