"""Environment configuration for live black-box SIP gate."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = ROOT / "config" / "local" / "freeswitch_zoiper.json"
VOICE_MANIFEST = ROOT / "tests" / "assets" / "blackbox_voice" / "manifest.json"
SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"
LIVE_E2E_ROOT = ROOT / ".run" / "live_e2e"


@dataclass(frozen=True)
class BlackboxConfig:
    sip_host: str
    sip_domain: str
    sip_port: int
    extension: str
    sip_user: str
    sip_password: str
    transport: str
    local_sip_port: int
    rtp_port_low: int
    rtp_port_high: int
    transport_mode: str
    stop_on_fail: bool
    sample_rate: int
    frame_ms: int
    bot_silence_ms: int
    barge_in_delay_ms: int
    max_call_s: float
    asr_command: str
    production_git_sha: str
    caller_git_sha: str

    @property
    def frame_bytes(self) -> int:
        return self.sample_rate * self.frame_ms // 1000


def _git_sha() -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def load_profile() -> dict:
    if DEFAULT_PROFILE.is_file():
        return json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
    return {}


def _is_lan_ipv4(addr: str) -> bool:
    if not addr or addr.startswith("127."):
        return False
    parts = addr.split(".")
    if len(parts) != 4:
        return False
    try:
        octets = [int(p) for p in parts]
    except ValueError:
        return False
    if octets[0] == 10:
        return True
    if octets[0] == 192 and octets[1] == 168:
        return True
    if octets[0] == 172 and 16 <= octets[1] <= 31:
        return True
    return False


def _loopback_fs_reachable(port: int = 5060) -> bool:
    import socket as _socket

    try:
        probe = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        probe.settimeout(0.5)
        ok = probe.connect_ex(("127.0.0.1", port)) == 0
        probe.close()
        return ok
    except OSError:
        return False


def _host_reachable(host: str, port: int = 5060) -> bool:
    import socket as _socket

    if host in {"127.0.0.1", "localhost"}:
        return _loopback_fs_reachable(port)
    try:
        probe = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        probe.settimeout(0.5)
        ok = probe.connect_ex((host, port)) == 0
        probe.close()
        return ok
    except OSError:
        return False


def is_docker_internal_smoke() -> bool:
    return os.environ.get("IMVERA_INTERNAL_DOCKER_SMOKE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def load_docker_internal_config() -> BlackboxConfig:
    """Phase A: pyVoIP caller inside docker-compose network (diagnostic only)."""
    host = os.environ.get("FS_SIP_HOST", "freeswitch").strip()
    port = int(os.environ.get("FS_SIP_PORT", "5060"))
    profile = load_profile()
    sip_domain = (
        os.environ.get("IMVERA_LIVE_SIP_DOMAIN")
        or profile.get("sip_host")
        or host
    ).strip()
    return BlackboxConfig(
        sip_host=host,
        sip_domain=sip_domain,
        sip_port=port,
        extension=os.environ.get("IMVERA_LIVE_EXTENSION", "7000"),
        sip_user=os.environ.get("FS_GATE_USER", "fs-gate-caller"),
        sip_password=os.environ.get("FS_GATE_PASSWORD", "gate"),
        transport=os.environ.get("IMVERA_LIVE_SIP_TRANSPORT", "udp"),
        local_sip_port=int(os.environ.get("IMVERA_LIVE_LOCAL_SIP_PORT", "5088")),
        rtp_port_low=int(os.environ.get("IMVERA_LIVE_RTP_LOW", "15000")),
        rtp_port_high=int(os.environ.get("IMVERA_LIVE_RTP_HIGH", "15100")),
        transport_mode="docker_internal",
        stop_on_fail=os.environ.get("IMVERA_LIVE_STOP_ON_FAIL", "1") not in {"0", "false", "no"},
        sample_rate=int(os.environ.get("IMVERA_LIVE_SAMPLE_RATE", "8000")),
        frame_ms=int(os.environ.get("IMVERA_LIVE_FRAME_MS", "20")),
        bot_silence_ms=int(os.environ.get("IMVERA_LIVE_BOT_SILENCE_MS", "1600")),
        barge_in_delay_ms=int(os.environ.get("IMVERA_LIVE_BARGE_IN_MS", "500")),
        max_call_s=float(os.environ.get("IMVERA_LIVE_MAX_CALL_S", "180")),
        asr_command=os.environ.get("IMVERA_BLACKBOX_ASR_CMD", ""),
        production_git_sha=_git_sha(),
        caller_git_sha=_git_sha(),
    )


def _live_media_host() -> str:
    """Current Mac LAN IP used as FreeSWITCH domain / Zoiper host (lab source of truth)."""
    try:
        from scripts.local_sip_config import detect_media_host

        return (detect_media_host() or "").strip()
    except Exception:
        return ""


def _refresh_stale_profile_host(live_host: str) -> None:
    """Rewrite gitignored freeswitch_zoiper.json when LAN IP drifted (no secrets changed)."""
    if not live_host or not DEFAULT_PROFILE.is_file():
        return
    try:
        data = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if (data.get("sip_host") or "").strip() == live_host:
        return
    data["sip_host"] = live_host
    DEFAULT_PROFILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_config() -> BlackboxConfig:
    if is_docker_internal_smoke():
        return load_docker_internal_config()
    profile = load_profile()
    profile_host = (profile.get("sip_host") or "").strip()
    env_host = (os.environ.get("IMVERA_LIVE_SIP_HOST") or "").strip()
    env_domain = (os.environ.get("IMVERA_LIVE_SIP_DOMAIN") or "").strip()
    port = int(os.environ.get("IMVERA_LIVE_SIP_PORT", profile.get("sip_port", 5060)))

    live_host = _live_media_host()
    # Prefer env, else reachable profile, else live LAN (detect_media_host). Stale
    # gitignored sip_host (e.g. old 192.168.1.64) must not become FS auth realm.
    preferred_host = env_host or profile_host or live_host or "127.0.0.1"
    if preferred_host not in {"127.0.0.1", "localhost"} and not _host_reachable(
        preferred_host, port
    ):
        if live_host and _host_reachable(live_host, port):
            preferred_host = live_host
            _refresh_stale_profile_host(live_host)
        elif live_host and _is_lan_ipv4(live_host):
            preferred_host = live_host
            _refresh_stale_profile_host(live_host)

    sip_domain = (env_domain or preferred_host or live_host or "127.0.0.1").strip()

    if preferred_host in {"127.0.0.1", "localhost"}:
        signal_host = preferred_host
    elif _host_reachable(preferred_host, port):
        signal_host = preferred_host
    elif _loopback_fs_reachable(port):
        signal_host = "127.0.0.1"
        if _is_lan_ipv4(preferred_host):
            sip_domain = preferred_host
        elif live_host and _is_lan_ipv4(live_host):
            sip_domain = live_host
    else:
        signal_host = preferred_host

    if signal_host in {"127.0.0.1", "localhost"} and _is_lan_ipv4(sip_domain):
        pass  # realm stays on LAN domain for FS directory lookup
    elif not sip_domain:
        sip_domain = signal_host
    sip_user = (
        os.environ.get("IMVERA_LIVE_SIP_USER")
        or profile.get("username")
        or os.environ.get("FS_GATE_USER", "fs-gate-caller")
    )
    sip_password = (
        os.environ.get("IMVERA_LIVE_SIP_PASSWORD")
        or profile.get("password")
        or os.environ.get("FS_GATE_PASSWORD", "gate")
    )
    return BlackboxConfig(
        sip_host=signal_host,
        sip_domain=sip_domain,
        sip_port=port,
        extension=os.environ.get("IMVERA_LIVE_EXTENSION", profile.get("dial_number", "7000")),
        sip_user=sip_user,
        sip_password=sip_password,
        transport=os.environ.get("IMVERA_LIVE_SIP_TRANSPORT", profile.get("transport", "udp")),
        local_sip_port=int(os.environ.get("IMVERA_LIVE_LOCAL_SIP_PORT", "5088")),
        rtp_port_low=int(os.environ.get("IMVERA_LIVE_RTP_LOW", "15000")),
        rtp_port_high=int(os.environ.get("IMVERA_LIVE_RTP_HIGH", "15100")),
        transport_mode=os.environ.get("IMVERA_LIVE_TRANSPORT", "local"),
        stop_on_fail=os.environ.get("IMVERA_LIVE_STOP_ON_FAIL", "1") not in {"0", "false", "no"},
        sample_rate=int(os.environ.get("IMVERA_LIVE_SAMPLE_RATE", "8000")),
        frame_ms=int(os.environ.get("IMVERA_LIVE_FRAME_MS", "20")),
        bot_silence_ms=int(os.environ.get("IMVERA_LIVE_BOT_SILENCE_MS", "1600")),
        barge_in_delay_ms=int(os.environ.get("IMVERA_LIVE_BARGE_IN_MS", "500")),
        max_call_s=float(os.environ.get("IMVERA_LIVE_MAX_CALL_S", "180")),
        asr_command=os.environ.get("IMVERA_BLACKBOX_ASR_CMD", ""),
        production_git_sha=_git_sha(),
        caller_git_sha=_git_sha(),
    )
