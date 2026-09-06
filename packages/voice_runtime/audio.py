"""PCM framing, resampling helpers, and audio envelope."""

from __future__ import annotations

from dataclasses import dataclass


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
    """Linear resampler with carry buffer for streaming blocks."""

    def __init__(self, source_rate: int, target_rate: int) -> None:
        if source_rate <= 0 or target_rate <= 0:
            raise ValueError("rates must be positive")
        self.source_rate = source_rate
        self.target_rate = target_rate
        self._ratio = target_rate / source_rate
        self._carry = b""

    def process(self, pcm_s16le: bytes) -> bytes:
        if self.source_rate == self.target_rate:
            return pcm_s16le
        data = self._carry + pcm_s16le
        if len(data) < 4:
            self._carry = data
            return b""
        import array

        samples = array.array("h")
        samples.frombytes(data[: len(data) - (len(data) % 2)])
        self._carry = data[len(samples) * 2 :]
        if not samples:
            return b""
        out_len = max(1, int(len(samples) * self._ratio))
        out = array.array("h", [0] * out_len)
        for i in range(out_len):
            src_idx = i / self._ratio
            j = int(src_idx)
            if j + 1 < len(samples):
                frac = src_idx - j
                out[i] = int(samples[j] * (1 - frac) + samples[j + 1] * frac)
            else:
                out[i] = samples[min(j, len(samples) - 1)]
        return out.tobytes()
