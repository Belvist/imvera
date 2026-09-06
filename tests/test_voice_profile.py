"""Voice profile config loading."""

from __future__ import annotations

import os

import pytest

from packages.voice_runtime.profile import audio_settings, load_profile


def test_audio_settings_sip_lab_defaults() -> None:
    load_profile.cache_clear()
    audio = audio_settings()
    assert audio["internal_sample_rate"] == 16000
    assert audio["inject_format"] == "slin48"
    assert audio["capture_format"] == "slin16"
    assert audio["output_sample_rate"] == 48000
    assert "slin48" in audio["sip_codecs"]


def test_inject_format_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    load_profile.cache_clear()
    monkeypatch.setenv("IMVERA_INJECT_FORMAT", "slin24")
    audio = audio_settings()
    assert audio["inject_format"] == "slin24"
