"""Pre-rendered opening phrase PCM — instant first audio on warm calls."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / ".run" / "cache"


@dataclass(frozen=True)
class CachedOpening:
    text: str
    pcm_s16le: bytes
    sample_rate: int
    engine: str = ""


def _cache_enabled() -> bool:
    return os.environ.get("IMVERA_OPENING_CACHE", "1").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def expected_tts_engine() -> str:
    return os.environ.get("IMVERA_TTS_MODEL_REVISION", "").strip()


def cache_path(text: str, engine: str = "") -> Path:
    material = f"{engine}\n{text}" if engine else text
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"opening_{digest}.json"


def save_opening(text: str, pcm: bytes, sample_rate: int, engine: str = "") -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    resolved = engine.strip() or expected_tts_engine()
    path = cache_path(text, resolved)
    payload = {
        "text": text,
        "sample_rate": sample_rate,
        "engine": resolved,
        "pcm_b64": base64.b64encode(pcm).decode("ascii"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def load_opening(text: str) -> CachedOpening | None:
    if not _cache_enabled():
        return None
    expected = expected_tts_engine()
    path = cache_path(text, expected)
    if not path.exists():
        # Legacy text-only key — never play unfingerprinted / macos_say PCM.
        legacy = cache_path(text)
        if legacy != path and legacy.exists():
            legacy.unlink(missing_ok=True)
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("text") != text:
        return None
    engine = str(data.get("engine") or "")
    if not engine or "macos_say" in engine:
        return None
    if expected and engine != expected:
        return None
    pcm_b64 = data.get("pcm_b64")
    if not pcm_b64:
        return None
    return CachedOpening(
        text=text,
        pcm_s16le=base64.b64decode(pcm_b64),
        sample_rate=int(data.get("sample_rate", 24000)),
        engine=engine,
    )
