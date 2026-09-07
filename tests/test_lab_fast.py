"""Lab fast TTS env helpers."""

from __future__ import annotations

from services.tts.lab_fast import apply_lab_fast_env, lab_fast_tts_enabled


def test_lab_fast_default_on(monkeypatch) -> None:
    monkeypatch.delenv("IMVERA_LAB_FAST_TTS", raising=False)
    assert lab_fast_tts_enabled() is True


def test_apply_lab_fast_sets_silero(monkeypatch) -> None:
    monkeypatch.delenv("IMVERA_TTS_ENGINE", raising=False)
    monkeypatch.delenv("IMVERA_SILERO_LAB_ACK", raising=False)
    env = apply_lab_fast_env({})
    assert env["IMVERA_TTS_ENGINE"] == "silero_lab"
    assert env["IMVERA_SILERO_LAB_ACK"] == "1"
    assert env["IMVERA_OPENING_CACHE"] == "1"


def test_lab_fast_respects_explicit_engine(monkeypatch) -> None:
    monkeypatch.setenv("IMVERA_TTS_ENGINE", "mlx_customvoice")
    env = apply_lab_fast_env({"IMVERA_TTS_ENGINE": "mlx_customvoice"})
    assert env["IMVERA_TTS_ENGINE"] == "mlx_customvoice"
