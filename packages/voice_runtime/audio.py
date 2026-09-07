"""PCM framing, resampling helpers, and audio envelope."""

from __future__ import annotations

import array
import math
import struct
from dataclasses import dataclass


def pcm_rms_s16le(pcm: bytes) -> float:
    """Root-mean-square of signed 16-bit mono PCM (0 = silence)."""
    if len(pcm) < 2:
        return 0.0
    count = len(pcm) // 2
    samples = struct.unpack(f"<{count}h", pcm[: count * 2])
    if not samples:
        return 0.0
    mean_sq = sum(s * s for s in samples) / len(samples)
    return math.sqrt(mean_sq)


def pcm16_frame_bytes(sample_rate: int, frame_ms: int = 20) -> int:
    if sample_rate <= 0 or frame_ms <= 0:
        raise ValueError("positive sample rate and frame duration required")
    samples, remainder = divmod(sample_rate * frame_ms, 1000)
    if remainder:
        raise ValueError("frame duration must contain whole samples")
    return samples * 2


@dataclass(frozen=True)
class AudioEnvelope:
    call_id: str
    generation_id: str
    phrase_id: str
    sequence: int
    sample_rate: int
    pcm_s16le: bytes


def belongs_to_active_output(
    chunk: AudioEnvelope, call_id: str, generation_id: str
) -> bool:
    return chunk.call_id == call_id and chunk.generation_id == generation_id


class StatefulResampler:
    """Linear resampler — preserves fractional source phase across chunks."""

    def __init__(self, source_rate: int, target_rate: int) -> None:
        if source_rate <= 0 or target_rate <= 0:
            raise ValueError("rates must be positive")
        self.source_rate = source_rate
        self.target_rate = target_rate
        self._step = source_rate / target_rate
        self._carry = b""
        self._samples: array.array = array.array("h")
        self._out_phase = 0.0

    def process(self, pcm_s16le: bytes) -> bytes:
        if self.source_rate == self.target_rate:
            return pcm_s16le
        self._append_pcm(pcm_s16le)
        return self._emit_available()

    def flush(self) -> bytes:
        if self.source_rate == self.target_rate:
            tail = self._carry
            self._carry = b""
            return tail
        out = array.array("h")
        if self._samples:
            while self._out_phase < len(self._samples):
                j = min(int(self._out_phase), len(self._samples) - 1)
                if j + 1 < len(self._samples):
                    frac = self._out_phase - j
                    s0 = self._samples[j]
                    s1 = self._samples[j + 1]
                    out.append(int(s0 * (1.0 - frac) + s1 * frac))
                else:
                    out.append(self._samples[j])
                self._out_phase += self._step
        self._samples = array.array("h")
        self._carry = b""
        self._out_phase = 0.0
        return out.tobytes()

    def _append_pcm(self, pcm_s16le: bytes) -> None:
        data = self._carry + pcm_s16le
        if len(data) < 2:
            self._carry = data
            return
        even_len = len(data) - (len(data) % 2)
        chunk = array.array("h")
        chunk.frombytes(data[:even_len])
        self._carry = data[even_len:]
        self._samples.extend(chunk)

    def _emit_available(self) -> bytes:
        out = array.array("h")
        while self._out_phase + 1 < len(self._samples):
            j = int(self._out_phase)
            frac = self._out_phase - j
            s0 = self._samples[j]
            s1 = self._samples[j + 1]
            out.append(int(s0 * (1.0 - frac) + s1 * frac))
            self._out_phase += self._step
        drop = int(self._out_phase)
        if drop > 0:
            self._samples = self._samples[drop:]
            self._out_phase -= drop
        return out.tobytes()
