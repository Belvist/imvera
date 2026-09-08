"""Generate LiveKit Docker Desktop runtime configs with LAN NAT addresses."""

from __future__ import annotations

import os
import platform
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = ROOT / "infra" / "livekit" / ".runtime"
MAC_TEMPLATE = ROOT / "infra" / "livekit" / "livekit.mac.yaml"
SERVER_OUT = RUNTIME_DIR / "livekit.server.yaml"
SIP_OUT = RUNTIME_DIR / "sip.mac.yaml"


def media_ip() -> str:
    env = os.environ.get("LIVEKIT_NODE_IP", "").strip()
    if env:
        return env
    from scripts.local_sip_config import detect_media_host

    return detect_media_host()


def sip_announced_port() -> int:
    return int(os.environ.get("LIVEKIT_SIP_PORT", "5065"))


def write_mac_runtime_configs() -> tuple[Path, Path]:
    """Write server + SIP configs advertising the host LAN IP (not Docker bridge)."""
    if platform.system() != "Darwin":
        raise RuntimeError("Mac runtime configs are for Darwin only")

    ip = media_ip()
    sip_port = sip_announced_port()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    base = yaml.safe_load(MAC_TEMPLATE.read_text(encoding="utf-8"))
    rtc = base.setdefault("rtc", {})
    rtc["use_external_ip"] = True
    rtc["node_ip"] = ip
    SERVER_OUT.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")

    sip_cfg = {
        "api_key": "devkey",
        "api_secret": "secret",
        "ws_url": "ws://livekit-server:7880",
        "redis": {"address": "host.docker.internal:6379"},
        "sip_port": sip_port,
        "sip_port_listen": 5060,
        "rtp_port": "10000-10100",
        "nat_1_to_1_ip": ip,
        "media_nat_1_to_1_ip": ip,
        "logging": {"level": "debug"},
    }
    SIP_OUT.write_text(yaml.safe_dump(sip_cfg, sort_keys=False), encoding="utf-8")
    return SERVER_OUT, SIP_OUT


def ensure_mac_runtime_configs() -> tuple[Path, Path] | None:
    if platform.system() != "Darwin":
        return None
    return write_mac_runtime_configs()
