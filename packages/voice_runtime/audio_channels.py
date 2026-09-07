"""Duplex audio helpers — client uplink vs Vera downlink (MossVoice LEFT=caller)."""

from __future__ import annotations

import array


def extract_client_uplink(pcm_s16le: bytes, *, channels: int = 1) -> bytes:
    """Return mono client mic from interleaved PCM.

    Stereo convention (record_stereo / MossVoice): channel 0 = caller, 1 = Vera.
    """
    if channels <= 1 or not pcm_s16le:
        return pcm_s16le
    samples = array.array("h")
    samples.frombytes(pcm_s16le[: len(pcm_s16le) - (len(pcm_s16le) % 2)])
    if not samples:
        return b""
    left = array.array("h", (samples[i] for i in range(0, len(samples), channels)))
    return left.tobytes()
