#!/usr/bin/env python3
"""Start self-hosted LiveKit + LiveKit SIP + Redis and print network summary."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "infra" / "livekit" / "docker-compose.yml"
SIP_YAML = ROOT / "infra" / "livekit" / "sip.yaml"
LIVEKIT_YAML = ROOT / "infra" / "livekit" / "livekit.yaml"


def _detect_public_ip() -> str:
    env_ip = os.environ.get("LIVEKIT_NODE_IP", "").strip()
    if env_ip:
        return env_ip
    try:
        r = httpx.get("https://api.ipify.org", timeout=2.0)
        if r.status_code == 200:
            return r.text.strip()
    except httpx.HTTPError:
        pass
    return "unknown (set LIVEKIT_NODE_IP)"


def _print_startup_banner() -> None:
    sip_cfg = yaml.safe_load(SIP_YAML.read_text(encoding="utf-8")) if SIP_YAML.exists() else {}
    lk_cfg = yaml.safe_load(LIVEKIT_YAML.read_text(encoding="utf-8")) if LIVEKIT_YAML.exists() else {}
    rtc = lk_cfg.get("rtc") or {}
    public_ip = _detect_public_ip()
    print("--- LiveKit startup network summary ---")
    print(f"  detected_public_ip: {public_ip}")
    print(f"  sip_listen: 0.0.0.0:{sip_cfg.get('sip_port', 5060)} (UDP+TCP)")
    print(f"  sip_rtp_range: {sip_cfg.get('rtp_port', '10000-20000')} UDP")
    print(f"  sip_use_external_ip: {sip_cfg.get('use_external_ip', False)}")
    print(f"  livekit_signaling: :{lk_cfg.get('port', 7880)}/TCP")
    print(f"  livekit_rtc_tcp: :{rtc.get('tcp_port', 7881)}/TCP")
    print(f"  livekit_rtc_udp_mux: :{rtc.get('udp_port', 7882)}/UDP  (IMVERA participant media)")
    print(f"  livekit_rtc_use_external_ip: {rtc.get('use_external_ip', False)}")
    print("  NOTE: 10000-20000 = SIP caller RTP; 7882 = WebRTC participant (NOT the same)")
    print("---------------------------------------")


def main() -> int:
    if not COMPOSE.exists():
        print(f"BLOCKED: missing {COMPOSE}", file=sys.stderr)
        return 1
    cmd = ["docker", "compose", "-f", str(COMPOSE), "up", "-d"]
    print("livekit-up:", " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        return rc
    _print_startup_banner()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
