"""Voice reference resolution for Qwen3-TTS zero-shot cloning."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

MANIFEST_NAME = "manifest.json"
TARGET_SAMPLE_RATE_HZ = 24000


def repo_root_from_config(config_path: Path) -> Path:
    return config_path.resolve().parents[1]


def manifest_path(config_path: Path) -> Path:
    return repo_root_from_config(config_path) / "config" / "voice_refs" / MANIFEST_NAME


def load_manifest(config_path: Path) -> dict[str, Any]:
    path = manifest_path(config_path)
    if not path.exists():
        return {"version": 1, "default_ref": None, "refs": []}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _ref_index(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["id"]: entry for entry in manifest.get("refs", []) if entry.get("id")}


def resolve_ref_path(raw: str, config_path: Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root_from_config(config_path) / path
    return path.resolve()


def lookup_manifest_ref(
    ref_id: str,
    config_path: Path,
    manifest: dict[str, Any] | None = None,
) -> tuple[Path | None, str | None]:
    data = manifest if manifest is not None else load_manifest(config_path)
    entry = _ref_index(data).get(ref_id)
    if entry is None:
        return None, None
    audio_raw = entry.get("file")
    if not audio_raw:
        return None, None
    audio_path = resolve_ref_path(str(audio_raw), config_path)
    if not audio_path.exists():
        return None, None
    ref_text = entry.get("ref_text")
    return audio_path, ref_text if ref_text else None


def resolve_tts_ref(
    tts_cfg: dict[str, Any],
    config_path: Path,
    *,
    force: bool = False,
) -> tuple[Path | None, str | None, str | None]:
    """
    Resolve reference audio for zero-shot cloning.

    Priority:
      1. IMVERA_TTS_USE_REF=0 → disabled
      2. IMVERA_TTS_REF_ID → manifest entry
      3. IMVERA_TTS_REF_AUDIO (+ optional IMVERA_TTS_REF_TEXT)
      4. tts.ref_id in config → manifest entry
      5. tts.ref_audio (+ tts.ref_text) in config
      6. manifest default_ref
    """
    if os.environ.get("IMVERA_TTS_USE_REF", "").strip().lower() in {"0", "false", "no"}:
        if not force:
            return None, None, None

    cfg_use_ref = tts_cfg.get("use_ref")
    if (
        not force
        and cfg_use_ref is False
        and not os.environ.get("IMVERA_TTS_USE_REF", "").strip()
        and not os.environ.get("IMVERA_TTS_REF_ID", "").strip()
        and not os.environ.get("IMVERA_TTS_REF_AUDIO", "").strip()
    ):
        return None, None, None

    manifest = load_manifest(config_path)

    env_ref_id = os.environ.get("IMVERA_TTS_REF_ID", "").strip()
    if env_ref_id:
        path, text = lookup_manifest_ref(env_ref_id, config_path, manifest)
        if path is not None:
            return path, text, env_ref_id

    env_audio = os.environ.get("IMVERA_TTS_REF_AUDIO", "").strip()
    if env_audio:
        path = resolve_ref_path(env_audio, config_path)
        env_text = os.environ.get("IMVERA_TTS_REF_TEXT", "").strip() or None
        if path.exists():
            return path, env_text, None
        return None, None, None

    cfg_ref_id = (tts_cfg.get("ref_id") or "").strip()
    if cfg_ref_id:
        path, text = lookup_manifest_ref(cfg_ref_id, config_path, manifest)
        if path is not None:
            return path, text, cfg_ref_id

    ref_audio = tts_cfg.get("ref_audio")
    if ref_audio:
        path = resolve_ref_path(str(ref_audio), config_path)
        ref_text = tts_cfg.get("ref_text")
        text = ref_text.strip() if isinstance(ref_text, str) and ref_text.strip() else None
        if path.exists():
            return path, text, cfg_ref_id or None
        return None, None, None

    default_ref = manifest.get("default_ref")
    if default_ref:
        path, text = lookup_manifest_ref(str(default_ref), config_path, manifest)
        if path is not None:
            return path, text, str(default_ref)

    return None, None, None
