"""Build identity for telephony /health and call-start logs."""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone

PROTOCOL_VERSION = 1
CONVERSATION_VERSION = "conversation_system_v2_observer_phase6"


def is_local_only() -> bool:
    raw = os.environ.get("MOSS_LOCAL_ONLY", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
        return out.strip() or "dev"
    except (OSError, subprocess.SubprocessError):
        return "dev"


def get_build_sha() -> str:
    return (os.environ.get("MOSS_BUILD_SHA") or _git_sha() or "dev").strip()


def get_build_time() -> str:
    env = (os.environ.get("MOSS_BUILD_TIME") or "").strip()
    if env:
        return env
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
