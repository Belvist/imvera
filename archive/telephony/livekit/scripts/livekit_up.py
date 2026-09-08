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
from scripts.livekit_compose import livekit_compose_file  # noqa: E402

COMPOSE = livekit_compose_file()
SIP_YAML = ROOT / "infra" / "livekit" / "sip.yaml"
LIVEKIT_YAML = ROOT / "infra" / "livekit" / "livekit.yaml"


def _detect_public_ip() -> str:
    env_ip = os.environ.get("LIVEKIT_NODE_IP", "").strip()
    if env_ip:
        return env_ip
    if "mac" in COMPOSE.name:
        from scripts.livekit_mac_runtime import media_ip

        return media_ip()
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

    if "mac" in COMPOSE.name:
        from scripts.livekit_mac_runtime import write_mac_runtime_configs

        server_cfg, sip_cfg = write_mac_runtime_configs()
        print(f"livekit-up: mac runtime configs → {server_cfg.name}, {sip_cfg.name}")

    pull_cmd = ["docker", "compose", "-f", str(COMPOSE), "pull"]
    print("livekit-up pull:", " ".join(pull_cmd))
    pull_rc = subprocess.call(pull_cmd)
    if pull_rc != 0:
        print("livekit-up: image pull failed", file=sys.stderr)
        return pull_rc

    cmd = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE),
        "up",
        "-d",
        "--pull",
        "always",
        "--force-recreate",
        "--remove-orphans",
    ]
    print("livekit-up:", " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        return rc
    _print_startup_banner()
    if "mac" in COMPOSE.name:
        from scripts.livekit_compose import livekit_sip_host_port

        host, port = livekit_sip_host_port()
        print(f"  mac_zoiper_sip: {host}:{port} → dial LIVEKIT_SIP_INBOUND_NUMBER")
        print("  run: make zoiper-livekit-info")
        gw_rc = subprocess.call([sys.executable, str(ROOT / "scripts" / "livekit_gateway_up.py")])
        if gw_rc != 0:
            print(
                "WARN: voice gateway not ready — Zoiper will ring but not answer "
                "(run: make livekit-gateway-up)",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
