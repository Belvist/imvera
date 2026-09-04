"""Deterministic PCM cache for planner control phrases (Track A1, Wave RT-1)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

# Keys align with golden_path.planner.PlannerAction control flows.
DEFAULT_PHRASE_KEYS = frozenset(
    {
        "WAIT",
        "REFUSAL",
        "CLOSE",
        "FATIGUE",
        "IDENTITY",
        "PRIVACY",
        "WHY_CALLING",
    }
)


class DeterministicPcmCache:
    """Lookup pre-synthesized mono int16 PCM @ 16 kHz — zero synthesis latency."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        sample_rate: int = 16000,
    ) -> None:
        env_root = os.environ.get("MOSS_PCM_CACHE_DIR", "").strip()
        self.root = Path(root or env_root or "voice_runtime/pcm_cache_store")
        self.sample_rate = sample_rate
        self._hits = 0
        self._misses = 0

    def _path_for(self, phrase_key: str) -> Path:
        safe = phrase_key.upper().replace("/", "_")
        return self.root / f"{safe}.pcm"

    def lookup(self, phrase_key: str) -> bytes | None:
        path = self._path_for(phrase_key)
        if not path.is_file():
            self._misses += 1
            return None
        data = path.read_bytes()
        if len(data) < 2:
            self._misses += 1
            return None
        self._hits += 1
        return data

    def store(self, phrase_key: str, pcm: bytes) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path_for(phrase_key)
        path.write_bytes(pcm)
        return path

    def metrics(self) -> Mapping[str, int]:
        return {"cache_hit": self._hits, "cache_miss": self._misses}
