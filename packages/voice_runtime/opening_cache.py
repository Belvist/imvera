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


def _cache_enabled() -> bool:
    return os.environ.get("IMVERA_OPENING_CACHE", "1").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def cache_path(text: str) -> Path:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"opening_{digest}.json"


def save_opening(text: str, pcm: bytes, sample_rate: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(text)
    payload = {
        "text": text,
        "sample_rate": sample_rate,
        "pcm_b64": base64.b64encode(pcm).decode("ascii"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def load_opening(text: str) -> CachedOpening | None:
    if not _cache_enabled():
        return None
    path = cache_path(text)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("text") != text:
        return None
    pcm_b64 = data.get("pcm_b64")
    if not pcm_b64:
        return None
    return CachedOpening(
        text=text,
        pcm_s16le=base64.b64decode(pcm_b64),
        sample_rate=int(data.get("sample_rate", 24000)),
    )
