"""TTS voice reference resolution tests (no MLX required)."""

from __future__ import annotations

from pathlib import Path

import yaml

from services.tts.voice_refs import (
    load_manifest,
    lookup_manifest_ref,
    manifest_path,
    resolve_ref_path,
    resolve_tts_ref,
)

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "voice-m5.yaml"


def _tts_cfg() -> dict:
    with CFG.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["models"]["tts"]


def test_manifest_exists_with_default_ref() -> None:
    manifest = load_manifest(CFG)
    assert manifest_path(CFG).exists()
    assert manifest.get("default_ref") == "fleurs_ru_female_1"
    ids = {r["id"] for r in manifest["refs"]}
    assert "fleurs_ru_female_1" in ids
    assert "bootstrap_vivian_ru" in ids


def test_manifest_entries_have_license_and_ref_text() -> None:
    manifest = load_manifest(CFG)
    for entry in manifest["refs"]:
        assert entry.get("ref_text")
        assert entry.get("license")
        assert entry.get("file")
        path = resolve_ref_path(entry["file"], CFG)
        assert path.exists(), f"missing wav for {entry['id']}"


def test_lookup_manifest_ref() -> None:
    path, text = lookup_manifest_ref("bootstrap_serena_ru", CFG)
    assert path is not None and path.exists()
    assert text and "лекарства" in text


def test_resolve_tts_ref_from_config() -> None:
    path, text, ref_id = resolve_tts_ref(_tts_cfg(), CFG)
    assert ref_id == "fleurs_ru_female_1"
    assert path is not None and path.name == "fleurs_ru_female_1.wav"
    assert text and "китая" in text


def test_resolve_tts_ref_env_override(monkeypatch) -> None:
    monkeypatch.setenv("IMVERA_TTS_REF_ID", "bootstrap_vivian_ru")
    path, text, ref_id = resolve_tts_ref(_tts_cfg(), CFG)
    assert ref_id == "bootstrap_vivian_ru"
    assert path is not None and "bootstrap_vivian" in path.name
    assert text and "Вера" in text


def test_resolve_tts_ref_disabled(monkeypatch) -> None:
    monkeypatch.setenv("IMVERA_TTS_USE_REF", "0")
    path, text, ref_id = resolve_tts_ref(_tts_cfg(), CFG)
    assert path is None and text is None and ref_id is None


def test_resolve_tts_ref_env_audio(monkeypatch, tmp_path) -> None:
    wav = tmp_path / "custom.wav"
    wav.write_bytes(b"RIFF")
    monkeypatch.setenv("IMVERA_TTS_REF_AUDIO", str(wav))
    monkeypatch.setenv("IMVERA_TTS_REF_TEXT", "тестовая фраза")
    monkeypatch.delenv("IMVERA_TTS_REF_ID", raising=False)
    path, text, _ = resolve_tts_ref(_tts_cfg(), CFG)
    assert path == wav.resolve()
    assert text == "тестовая фраза"
