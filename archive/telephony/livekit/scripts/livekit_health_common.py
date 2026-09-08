"""Shared LiveKit health checks — media vs AI modes."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import httpx
import yaml

from scripts.livekit_compose import livekit_compose_file, livekit_sip_host_port

ROOT = Path(__file__).resolve().parent.parent
LIVEKIT_YAML = ROOT / "infra" / "livekit" / "livekit.yaml"
SIP_YAML = ROOT / "infra" / "livekit" / "sip.yaml"
MAC_SERVER_YAML = ROOT / "infra" / "livekit" / ".runtime" / "livekit.server.yaml"
MAC_SIP_YAML = ROOT / "infra" / "livekit" / ".runtime" / "sip.mac.yaml"
GATEWAY = os.environ.get("IMVERA_VOICE_GATEWAY_HTTP", "http://127.0.0.1:9200")

MEDIA_COMPONENTS = (
    "redis",
    "livekit_api",
    "livekit_rtc",
    "sip_signaling",
    "sip_rtp_config",
    "gateway_media",
)

AI_COMPONENTS = ("stt", "tts", "llm")


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


def detect_public_ip() -> str:
    env_ip = os.environ.get("LIVEKIT_NODE_IP", "").strip()
    if env_ip:
        return env_ip
    if livekit_compose_file().name.endswith("mac.yml") and MAC_SIP_YAML.exists():
        sip_cfg = _load_yaml(MAC_SIP_YAML)
        nat_ip = sip_cfg.get("nat_1_to_1_ip", "")
        if nat_ip:
            return str(nat_ip)
    try:
        r = httpx.get("https://api.ipify.org", timeout=2.0)
        if r.status_code == 200:
            return r.text.strip()
    except httpx.HTTPError:
        pass
    return "unknown"


def run_checks(mode: str = "all") -> list[tuple[str, bool, str]]:
    mac_lab = livekit_compose_file().name.endswith("mac.yml")
    lk_path = MAC_SERVER_YAML if mac_lab and MAC_SERVER_YAML.exists() else LIVEKIT_YAML
    sip_path = MAC_SIP_YAML if mac_lab and MAC_SIP_YAML.exists() else SIP_YAML
    lk_cfg = _load_yaml(lk_path)
    sip_cfg = _load_yaml(sip_path)
    checks: list[tuple[str, bool, str]] = []

    if mode in {"media", "all"}:
        _, sip_port = livekit_sip_host_port()
        checks.append(("redis", _port_open("127.0.0.1", 6379), "6379/tcp"))
        try:
            r = httpx.get("http://127.0.0.1:7880/", timeout=3.0)
            checks.append(("livekit_api", r.status_code < 500, f"7880/tcp HTTP {r.status_code}"))
        except httpx.HTTPError as exc:
            checks.append(("livekit_api", False, str(exc)))

        rtc = lk_cfg.get("rtc") or {}
        udp_port = int(rtc.get("udp_port", 7882))
        tcp_port = int(rtc.get("tcp_port", 7881))
        use_ext = bool(rtc.get("use_external_ip", False))
        rtc_ok = _port_open("127.0.0.1", tcp_port) if mac_lab else use_ext and _port_open(
            "127.0.0.1", tcp_port
        )
        rtc_detail = (
            f"config tcp={tcp_port} udp_mux={udp_port} use_external_ip={use_ext} "
            "(flow proof: make livekit-media-gate)"
        )
        checks.append(("livekit_rtc", rtc_ok, rtc_detail))
        checks.append(("sip_signaling", _port_open("127.0.0.1", sip_port), f"{sip_port}/tcp"))
        public_ip = detect_public_ip()
        rtp = sip_cfg.get("rtp_port", "10000-20000")
        nat_ip = sip_cfg.get("nat_1_to_1_ip", "")
        use_sip_ext = bool(sip_cfg.get("use_external_ip", False))
        if mac_lab:
            use_sip_ext = bool(nat_ip)
        checks.append(
            (
                "sip_rtp_config",
                (use_sip_ext and public_ip != "unknown") or not use_sip_ext,
                f"nat_1_to_1_ip={nat_ip or 'unset'} rtp={rtp} sip_port={sip_port} advertised_ip={public_ip}",
            )
        )
        try:
            r = httpx.get(f"{GATEWAY}/health/ready", timeout=3.0)
            # Media gate: gateway process up; inference may be 503.
            ok = r.status_code in {200, 503}
            checks.append(("gateway_media", ok, f"{GATEWAY} HTTP {r.status_code}"))
        except httpx.HTTPError as exc:
            checks.append(("gateway_media", False, str(exc)))

    if mode in {"ai", "all"}:
        stt = os.environ.get("IMVERA_STT_URL", "http://127.0.0.1:9101")
        tts = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
        llm = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103")
        for name, url in (("stt", stt), ("tts", tts), ("llm", llm)):
            try:
                r = httpx.get(f"{url.rstrip('/')}/health/ready", timeout=2.0)
                checks.append((name, r.status_code == 200, f"{url} HTTP {r.status_code}"))
            except httpx.HTTPError as exc:
                checks.append((name, False, str(exc)))

    return checks
