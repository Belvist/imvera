"""Voice profile YAML — audio and SIP lab settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = "config/voice-m5.yaml"

_FORMAT_SAMPLE_RATES: dict[str, int] = {
    "slin": 8000,
    "slin12": 12000,
    "slin16": 16000,
    "slin24": 24000,
    "slin32": 32000,
    "slin44": 44100,
    "slin48": 48000,
    "slin96": 96000,
    "slin192": 192000,
    "ulaw": 8000,
    "alaw": 8000,
}


def profile_path() -> Path:
    override = os.environ.get("IMVERA_VOICE_PROFILE_PATH")
    if override:
        path = Path(override)
        return path if path.is_absolute() else ROOT / path
    return ROOT / DEFAULT_PROFILE


@lru_cache(maxsize=1)
def load_profile() -> dict[str, Any]:
    with profile_path().open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _format_sample_rate(fmt: str) -> int:
    return _FORMAT_SAMPLE_RATES.get(fmt, 16000)


def audio_settings() -> dict[str, Any]:
    """Resolved audio settings with env overrides for telephony inject/capture."""
    audio = load_profile().get("audio") or {}
    inject_format = os.environ.get("IMVERA_INJECT_FORMAT") or str(
        audio.get("inject_format", "slin16")
    )
    capture_format = os.environ.get("IMVERA_CAPTURE_FORMAT") or str(
        audio.get("capture_format", "slin16")
    )
    internal_sr = int(
        os.environ.get("IMVERA_INTERNAL_SAMPLE_RATE")
        or audio.get("internal_sample_rate", 16000)
    )
    output_sr = int(
        audio.get("output_sample_rate") or _format_sample_rate(inject_format)
    )
    frame_ms = int(audio.get("frame_ms", 20))
    sip_codecs = str(audio.get("sip_codecs", "g722,slin48,slin24,slin16"))
    sip_codecs_e2e = str(audio.get("sip_codecs_e2e", "ulaw,alaw"))
    return {
        "internal_sample_rate": internal_sr,
        "output_sample_rate": output_sr,
        "inject_format": inject_format,
        "capture_format": capture_format,
        "frame_ms": frame_ms,
        "sip_codecs": sip_codecs,
        "sip_codecs_e2e": sip_codecs_e2e,
    }


def apply_audio_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Populate IMVERA_* audio env vars from profile (for voice_up subprocesses)."""
    out = dict(env or os.environ)
    audio = audio_settings()
    out.setdefault("IMVERA_INJECT_FORMAT", audio["inject_format"])
    out.setdefault("IMVERA_CAPTURE_FORMAT", audio["capture_format"])
    out.setdefault("IMVERA_INTERNAL_SAMPLE_RATE", str(audio["internal_sample_rate"]))
    out.setdefault(
        "IMVERA_PLAYBACK_BUFFER_MS",
        str(load_profile().get("limits", {}).get("playback_buffer_ms", 60)),
    )
    return out
