"""Map PCM + transcript signals to asr_quality (ADR-003 wrapper).

GigaAM / mlx_audio STT backends do not expose logprobs/no_speech_prob on the worker
path, so we derive quality from audio energy, segment duration, and transcript shape.
"""

from __future__ import annotations

import math
import re
import struct
from typing import Literal

AsrQualityLabel = Literal["GOOD", "LOW", "UNUSABLE"]

# Telephony PCM s16le — conservative; tuned for 16 kHz lab path.
_MIN_DURATION_MS = 200
_MIN_RMS = 120.0
_LOW_RMS = 280.0
_SHORT_UTTERANCE_MS = 800


def pcm_rms_s16le(pcm: bytes) -> float:
    if len(pcm) < 2:
        return 0.0
    count = len(pcm) // 2
    samples = struct.unpack(f"<{count}h", pcm[: count * 2])
    if not samples:
        return 0.0
    mean_sq = sum(s * s for s in samples) / len(samples)
    return math.sqrt(mean_sq)


def _normalize_text(text: str) -> str:
    return re.sub(r"[^\wа-яА-ЯёЁ]+", "", text.strip(), flags=re.UNICODE).casefold()


def assess_asr_quality(
    pcm: bytes,
    *,
    sample_rate: int,
    duration_ms: int,
    text: str,
    generation_tokens: int | None = None,
) -> AsrQualityLabel:
    """Classify STT output for downstream clarify / retry policy."""
    del sample_rate  # reserved for future band-limited RMS checks

    rms = pcm_rms_s16le(pcm)
    cleaned = _normalize_text(text)

    if duration_ms < _MIN_DURATION_MS or len(pcm) < 320:
        return "UNUSABLE"
    if rms < _MIN_RMS:
        return "UNUSABLE"

    if not cleaned:
        return "LOW" if rms >= _LOW_RMS else "UNUSABLE"

    if len(cleaned) <= 1:
        return "LOW"

    if duration_ms < _SHORT_UTTERANCE_MS and len(cleaned) <= 2:
        return "LOW"

    if generation_tokens is not None and generation_tokens <= 2 and duration_ms < 1000:
        return "LOW"

    if rms < _LOW_RMS and len(cleaned) <= 3:
        return "LOW"

    return "GOOD"
