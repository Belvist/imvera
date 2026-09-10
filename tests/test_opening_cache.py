"""Opening phrase PCM cache."""

from __future__ import annotations

import json

from packages.voice_runtime.opening_cache import (
    cache_path,
    load_opening,
    save_opening,
)


def test_opening_cache_roundtrip(tmp_path, monkeypatch) -> None:
    import packages.voice_runtime.opening_cache as oc

    monkeypatch.setattr(oc, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("IMVERA_TTS_MODEL_REVISION", "silero_lab:silero:v5_ru:xenia")
    text = "Здравствуйте, это сервис Амвера, Даниил. Как вы себя чувствуете?"
    pcm = b"\x00\x01" * 100
    path = save_opening(text, pcm, 24000, engine="silero_lab:silero:v5_ru:xenia")
    assert path.exists()
    loaded = load_opening(text)
    assert loaded is not None
    assert loaded.text == text
    assert loaded.pcm_s16le == pcm
    assert loaded.sample_rate == 24000
    assert loaded.engine == "silero_lab:silero:v5_ru:xenia"


def test_opening_cache_miss_on_text_change(tmp_path, monkeypatch) -> None:
    import packages.voice_runtime.opening_cache as oc

    monkeypatch.setattr(oc, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("IMVERA_TTS_MODEL_REVISION", "silero_lab:silero:v5_ru:xenia")
    save_opening("phrase A", b"\x00\x00", 24000, engine="silero_lab:silero:v5_ru:xenia")
    assert load_opening("phrase B") is None


def test_opening_cache_disabled(monkeypatch, tmp_path) -> None:
    import packages.voice_runtime.opening_cache as oc

    monkeypatch.setattr(oc, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("IMVERA_TTS_MODEL_REVISION", "silero_lab:silero:v5_ru:xenia")
    save_opening("x", b"\x01", 24000, engine="silero_lab:silero:v5_ru:xenia")
    monkeypatch.setenv("IMVERA_OPENING_CACHE", "0")
    assert load_opening("x") is None


def test_opening_cache_rejects_macos_and_engine_mismatch(tmp_path, monkeypatch) -> None:
    import packages.voice_runtime.opening_cache as oc

    monkeypatch.setattr(oc, "CACHE_DIR", tmp_path)
    text = "hello"
    monkeypatch.setenv("IMVERA_TTS_MODEL_REVISION", "silero_lab:macos_say:Milena")
    save_opening(text, b"\x02\x00", 24000, engine="silero_lab:macos_say:Milena")
    assert load_opening(text) is None
    monkeypatch.setenv("IMVERA_TTS_MODEL_REVISION", "silero_lab:silero:v5_ru:xenia")
    save_opening(text, b"\x03\x00", 24000, engine="silero_lab:silero:v5_ru:xenia")
    loaded = load_opening(text)
    assert loaded is not None
    monkeypatch.setenv("IMVERA_TTS_MODEL_REVISION", "silero_lab:silero:v5_ru:baya")
    assert load_opening(text) is None


def test_cache_path_stable_digest() -> None:
    p1 = cache_path("hello", "silero_lab:silero:v5_ru:xenia")
    p2 = cache_path("hello", "silero_lab:silero:v5_ru:xenia")
    assert p1 == p2
    assert p1.name.startswith("opening_")
    assert cache_path("hello", "macos_say") != p1
