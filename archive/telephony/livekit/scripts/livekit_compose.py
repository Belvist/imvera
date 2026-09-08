"""Resolve LiveKit docker-compose file for current platform."""

from __future__ import annotations

import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINUX_COMPOSE = ROOT / "infra" / "livekit" / "docker-compose.yml"
MAC_COMPOSE = ROOT / "infra" / "livekit" / "docker-compose.mac.yml"


def livekit_compose_file() -> Path:
    if platform.system() == "Darwin" and MAC_COMPOSE.exists():
        return MAC_COMPOSE
    return LINUX_COMPOSE


def livekit_sip_host_port() -> tuple[str, int]:
    """Host-visible SIP endpoint for Zoiper / synthetic callers."""
    import json
    import os

    from scripts.local_sip_config import detect_media_host

    zoiper_json = ROOT / "config" / "local" / "zoiper.json"
    if zoiper_json.exists():
        data = json.loads(zoiper_json.read_text(encoding="utf-8"))
        lk = data.get("livekit") or {}
        if lk.get("sip_host") and lk.get("sip_port"):
            return str(lk["sip_host"]), int(lk["sip_port"])

    host = os.environ.get("LIVEKIT_SIP_HOST", detect_media_host())
    port = int(os.environ.get("LIVEKIT_SIP_PORT", "5065" if platform.system() == "Darwin" else "5060"))
    return host, port
