"""MediaAdapter — the realtime media-source contract (read.md G2).

The production path must NOT depend on a growing WAV file left by
``uuid_record`` (G2). It consumes a continuous PCM16/mono/16 kHz stream from
whichever transport delivers it (ESL media bug, WebSocket frames, RTP). All
transports implement the SAME contract so the VAD/turn loop never changes:

    adapter.frames_in()   -> list[int16]  NEW mono samples since last call
    adapter.rate          -> int          source sample rate (before resample)
    adapter.audio_bytes() -> int          payload bytes written so far
    adapter.broken        -> bool         source is garbage / failed
    adapter.close()       -> None         release the source

The current ``uuid_record`` tail-reader (LiveWavReader, dev-only) already
conforms; a WebSocket/MediaBug adapter must too. Callers MUST stop feeding
VAD/STT as soon as ``broken`` is True (a broken source once made the
assistant "hear" hallucinated speech).
"""
from __future__ import annotations

import abc


class MediaAdapter(abc.ABC):
    """Continuous mono-int16 media source (16 kHz canonical)."""

    SAMPLE_RATE = 16000

    def __init__(self):
        self.broken = False

    @abc.abstractmethod
    def frames_in(self, rate=SAMPLE_RATE):
        """New int16 mono samples since the last call, resampled to ``rate``.

        Returns ``[]`` while no valid media has arrived and after the source
        is proven broken — NEVER garbage. Must not raise on a transient read
        failure (return ``[]`` instead)."""

    @property
    @abc.abstractmethod
    def rate(self):
        """Native sample rate of the source (before resampling)."""

    @abc.abstractmethod
    def audio_bytes(self):
        """Payload bytes received so far (0 before the first valid block)."""

    def close(self):
        """Release the underlying source (file/socket). Idempotent; the
        default implementation is a no-op for stateless adapters."""


class NullMedia(MediaAdapter):
    """Test/silence adapter: always-empty stream, never broken."""

    def frames_in(self, rate=MediaAdapter.SAMPLE_RATE):
        return []

    @property
    def rate(self):
        return self.SAMPLE_RATE

    def audio_bytes(self):
        return 0