"""Codec-aware PCM output rates — one resample hop from TTS native to negotiated leg."""

from __future__ import annotations

import os

TTS_NATIVE_SAMPLE_RATE = 24000


def target_pcm_rate_for_codec(codec: str) -> int:
    """PCM rate sent to FreeSWITCH before RTP encode to ``codec``."""
    name = (codec or "").upper().replace(".", "").replace("-", "")
    if name in {"G722", "G7221"}:
        # G.722 wideband — FS/RTP leg is 16 kHz; keep TTS-native 24k on WS when possible.
        return 24000
    if name in {"PCMU", "ULAW", "PCMA", "ALAW", "G711"}:
        return 8000
    if name in {"OPUS"}:
        return 48000
    if name in {"SLIN48", "L16"}:
        return 48000
    if name in {"SLIN24"}:
        return 24000
    if name in {"SLIN16"}:
        return 16000
    return 16000


def negotiated_codec_name() -> str:
    return os.environ.get("IMVERA_NEGOTIATED_CODEC", "G722").strip() or "G722"


def bridge_audio_rates(codec: str | None = None) -> tuple[int, int]:
    """(capture_sr, playback_sr) for FS WebSocket bridge."""
    from packages.voice_runtime.profile import audio_settings

    audio = audio_settings()
    capture_sr = int(audio["internal_sample_rate"])
    codec_name = codec or negotiated_codec_name()
    override = os.environ.get("IMVERA_PLAYBACK_SAMPLE_RATE")
    playback_sr = int(override) if override else target_pcm_rate_for_codec(codec_name)
    return capture_sr, playback_sr


def resampler_chain_summary(
    *,
    tts_native_rate: int = TTS_NATIVE_SAMPLE_RATE,
    bridge_output_rate: int,
    negotiated_codec: str,
) -> dict[str, int | str]:
    codec_rate = target_pcm_rate_for_codec(negotiated_codec)
    hops: list[str] = [f"tts:{tts_native_rate}"]
    if tts_native_rate != bridge_output_rate:
        hops.append(f"bridge:{bridge_output_rate}")
    if bridge_output_rate != codec_rate and negotiated_codec.upper().startswith("G722"):
        hops.append("fs:g722@16000")
    return {
        "tts_native_rate": tts_native_rate,
        "bridge_output_rate": bridge_output_rate,
        "negotiated_codec": negotiated_codec,
        "codec_pcm_target": codec_rate,
        "resampler_hops": " → ".join(hops),
        "resampler_count": max(0, len(hops) - 1),
    }
