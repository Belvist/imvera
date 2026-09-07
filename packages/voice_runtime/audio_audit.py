"""Lab audio audit — full capture/STT dumps + trace ticks (IMVERA_AUDIO_AUDIT=1)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def audio_audit_enabled() -> bool:
    return os.environ.get("IMVERA_AUDIO_AUDIT", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def apply_audio_audit_env(env: dict[str, str]) -> dict[str, str]:
    """Enable end-to-end audio dumps for Zoiper lab debugging."""
    if env.get("IMVERA_AUDIO_AUDIT", "1").strip().lower() in {"0", "false", "no"}:
        return env
    env.setdefault("IMVERA_AUDIO_AUDIT", "1")
    env.setdefault("IMVERA_STT_DUMP", "1")
    env.setdefault("IMVERA_CAPTURE_DUMP", str(ROOT / ".run" / "captures" / "{call_id}.pcm"))
    return env
