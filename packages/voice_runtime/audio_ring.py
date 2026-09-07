"""Fixed-duration PCM ring buffer — raw inbound audio is never discarded."""

from __future__ import annotations


class AudioRingBuffer:
    """Keep the last ``max_ms`` of mono PCM16 at ``sample_rate`` Hz."""

    def __init__(
        self,
        sample_rate: int,
        max_ms: int = 4000,
        *,
        bytes_per_sample: int = 2,
    ) -> None:
        self.sample_rate = sample_rate
        self.bytes_per_sample = bytes_per_sample
        self._max_bytes = max(
            bytes_per_sample,
            sample_rate * bytes_per_sample * max_ms // 1000,
        )
        self._buf = bytearray()

    def push(self, pcm: bytes) -> None:
        if not pcm:
            return
        self._buf.extend(pcm)
        overflow = len(self._buf) - self._max_bytes
        if overflow > 0:
            del self._buf[:overflow]

    def snapshot(self) -> bytes:
        return bytes(self._buf)

    def clear(self) -> None:
        self._buf.clear()

    @property
    def byte_len(self) -> int:
        return len(self._buf)
