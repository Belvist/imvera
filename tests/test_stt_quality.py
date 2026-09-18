"""Unit tests for STT asr_quality wrapper (no live model)."""

from __future__ import annotations

import math
import struct

from services.stt.quality import assess_asr_quality, pcm_rms_s16le


def _sine_pcm(
    duration_ms: int, sample_rate: int = 16000, freq: float = 440.0, amp: float = 0.25
) -> bytes:
    n = int(sample_rate * duration_ms / 1000)
    samples = [int(amp * 32767 * math.sin(2 * math.pi * freq * i / sample_rate)) for i in range(n)]
    return struct.pack(f"<{len(samples)}h", *samples)


def _silence_pcm(duration_ms: int, sample_rate: int = 16000) -> bytes:
    n = int(sample_rate * duration_ms / 1000)
    return b"\x00\x00" * n


def test_pcm_rms_silence_and_tone() -> None:
    assert pcm_rms_s16le(_silence_pcm(100)) == 0.0
    tone = _sine_pcm(500)
    assert pcm_rms_s16le(tone) > 1000.0


def test_unusable_too_short_or_silent() -> None:
    assert (
        assess_asr_quality(
            _silence_pcm(100),
            sample_rate=16000,
            duration_ms=100,
            text="",
        )
        == "UNUSABLE"
    )
    assert (
        assess_asr_quality(
            _silence_pcm(500),
            sample_rate=16000,
            duration_ms=500,
            text="Д.",
        )
        == "UNUSABLE"
    )


def test_low_hallucination_on_tone() -> None:
    tone = _sine_pcm(500)
    assert assess_asr_quality(
        tone,
        sample_rate=16000,
        duration_ms=500,
        text="Д.",
        generation_tokens=2,
    ) in ("LOW", "UNUSABLE")


def test_good_wellness_phrases() -> None:
    speech_like = _sine_pcm(1200, amp=0.5)
    for phrase in ("хорошо", "не очень", "чувствую себя хорошо", "да"):
        assert (
            assess_asr_quality(
                speech_like,
                sample_rate=16000,
                duration_ms=1200,
                text=phrase,
                generation_tokens=8,
            )
            == "GOOD"
        )


def test_low_empty_on_quiet_segment() -> None:
    quiet = _sine_pcm(600, amp=0.01)
    assert (
        assess_asr_quality(
            quiet,
            sample_rate=16000,
            duration_ms=600,
            text="",
        )
        == "UNUSABLE"
    )
