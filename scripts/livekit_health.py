#!/usr/bin/env python3
"""Health check for self-hosted LiveKit stack — per-component status."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
LIVEKIT_YAML = ROOT / "infra" / "livekit" / "livekit.yaml"
SIP_YAML = ROOT / "infra" / "livekit" / "sip.yaml"
GATEWAY = os.environ.get("IMVERA_VOICE_GATEWAY_HTTP", "http://127.0.0.1:9200")


def _port_open(host: str, port: int, *, udp: bool = False) -> bool:
    if udp:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            sock.bind((host, port))
            sock.close()
            return True
        except OSError:
            return False
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except OSError:
        return False


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


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
    return "unknown"


def _check_redis() -> tuple[str, bool, str]:
    ok = _port_open("127.0.0.1", 6379)
    return ("redis", ok, "6379/tcp")


def _check_livekit_api() -> tuple[str, bool, str]:
    try:
        r = httpx.get("http://127.0.0.1:7880/", timeout=3.0)
        ok = r.status_code < 500
        return ("livekit_api", ok, f"7880/tcp HTTP {r.status_code}")
    except httpx.HTTPError as exc:
        return ("livekit_api", False, str(exc))


def _check_livekit_rtc(cfg: dict) -> tuple[str, bool, str]:
    rtc = cfg.get("rtc") or {}
    udp_port = rtc.get("udp_port", 7882)
    tcp_port = rtc.get("tcp_port", 7881)
    use_ext = rtc.get("use_external_ip", False)
    tcp_ok = _port_open("127.0.0.1", int(tcp_port))
    udp_ok = _port_open("0.0.0.0", int(udp_port), udp=True)
    detail = f"tcp={tcp_port} udp_mux={udp_port} use_external_ip={use_ext}"
    return ("livekit_rtc", tcp_ok and use_ext, detail)


def _check_sip_signaling() -> tuple[str, bool, str]:
    ok = _port_open("127.0.0.1", 5060)
    return ("sip_signaling", ok, "5060/tcp")


def _check_sip_rtp_config(sip_cfg: dict) -> tuple[str, bool, str]:
    use_ext = sip_cfg.get("use_external_ip", False)
    rtp = sip_cfg.get("rtp_port", "10000-20000")
    public_ip = _detect_public_ip()
    ok = use_ext and public_ip != "unknown"
    detail = f"use_external_ip={use_ext} rtp={rtp} advertised_ip={public_ip}"
    return ("sip_rtp_config", ok, detail)


def _check_gateway_webhook() -> tuple[str, bool, str]:
    try:
        r = httpx.get(f"{GATEWAY}/health/ready", timeout=3.0)
        return ("gateway_webhook", r.status_code in {200, 503}, f"{GATEWAY} HTTP {r.status_code}")
    except httpx.HTTPError as exc:
        return ("gateway_webhook", False, str(exc))


def _check_inference(name: str, url: str) -> tuple[str, bool, str]:
    try:
        r = httpx.get(f"{url.rstrip('/')}/health/ready", timeout=2.0)
        ok = r.status_code == 200
        return (name, ok, f"{url} HTTP {r.status_code}")
    except httpx.HTTPError as exc:
        return (name, False, str(exc))


def main() -> int:
    lk_cfg = _load_yaml(LIVEKIT_YAML)
    sip_cfg = _load_yaml(SIP_YAML)

    stt = os.environ.get("IMVERA_STT_URL", "http://127.0.0.1:9101")
    tts = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    llm = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103")

    checks = [
        _check_redis(),
        _check_livekit_api(),
        _check_livekit_rtc(lk_cfg),
        _check_sip_signaling(),
        _check_sip_rtp_config(sip_cfg),
        _check_gateway_webhook(),
        _check_inference("stt", stt),
        _check_inference("tts", tts),
        _check_inference("llm", llm),
    ]

    failed = []
    for name, ok, detail in checks:
        status = "OK" if ok else "FAIL"
        print(f"  {status:4} {name:18} {detail}")
        if not ok:
            failed.append(name)

    if failed:
        print(f"livekit-health: FAILED components: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("livekit-health: all components OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
