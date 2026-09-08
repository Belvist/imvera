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


def load_config() -> BlackboxConfig:
    profile = load_profile()
    host = os.environ.get("IMVERA_LIVE_SIP_HOST") or profile.get("sip_host") or "127.0.0.1"
    return BlackboxConfig(
        sip_host=host,
        sip_port=int(os.environ.get("IMVERA_LIVE_SIP_PORT", profile.get("sip_port", 5060))),
        extension=os.environ.get("IMVERA_LIVE_EXTENSION", profile.get("dial_number", "7000")),
        sip_user=os.environ.get(
            "IMVERA_LIVE_SIP_USER",
            os.environ.get("FS_GATE_USER", "fs-gate-caller"),
        ),
        sip_password=os.environ.get(
            "IMVERA_LIVE_SIP_PASSWORD",
            os.environ.get("FS_GATE_PASSWORD", "gate"),
        ),
        transport=os.environ.get("IMVERA_LIVE_SIP_TRANSPORT", profile.get("transport", "udp")),
        local_sip_port=int(os.environ.get("IMVERA_LIVE_LOCAL_SIP_PORT", "5088")),
        rtp_port_low=int(os.environ.get("IMVERA_LIVE_RTP_LOW", "15000")),
        rtp_port_high=int(os.environ.get("IMVERA_LIVE_RTP_HIGH", "15100")),
        transport_mode=os.environ.get("IMVERA_LIVE_TRANSPORT", "local"),
        stop_on_fail=os.environ.get("IMVERA_LIVE_STOP_ON_FAIL", "1") not in {"0", "false", "no"},
        sample_rate=int(os.environ.get("IMVERA_LIVE_SAMPLE_RATE", "8000")),
        frame_ms=int(os.environ.get("IMVERA_LIVE_FRAME_MS", "20")),
        bot_silence_ms=int(os.environ.get("IMVERA_LIVE_BOT_SILENCE_MS", "900")),
        barge_in_delay_ms=int(os.environ.get("IMVERA_LIVE_BARGE_IN_MS", "500")),
        max_call_s=float(os.environ.get("IMVERA_LIVE_MAX_CALL_S", "180")),
        asr_command=os.environ.get("IMVERA_BLACKBOX_ASR_CMD", ""),
        production_git_sha=_git_sha(),
        caller_git_sha=_git_sha(),
    )
