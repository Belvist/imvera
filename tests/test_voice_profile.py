"""Voice profile config loading."""

from __future__ import annotations

import pytest

from packages.voice_runtime.profile import audio_settings, load_profile


def test_audio_settings_sip_lab_defaults() -> None:
    load_profile.cache_clear()
    audio = audio_settings()
    assert audio["internal_sample_rate"] == 16000
    assert audio["inject_format"] == "slin24"
    assert audio["capture_format"] == "slin16"
    assert audio["output_sample_rate"] == 24000
    assert "g722" in audio["sip_codecs"]
    assert "ulaw" not in audio["sip_codecs"].split(",")
    assert audio["sip_codecs_e2e"] == "ulaw,alaw"


def test_inject_format_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    load_profile.cache_clear()
    monkeypatch.setenv("IMVERA_INJECT_FORMAT", "slin24")
    audio = audio_settings()
    assert audio["inject_format"] == "slin24"
