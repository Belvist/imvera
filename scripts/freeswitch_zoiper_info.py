#!/usr/bin/env python3
"""Zoiper → FreeSWITCH P0-A lab profile (ADR-013)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.local_sip_config import detect_media_host

ROOT = Path(__file__).resolve().parent.parent
PROFILE_JSON = ROOT / "config" / "local" / "freeswitch_zoiper.json"
DEFAULT_DIAL = "7000"
FS_PORT = 5060


def sync_freeswitch_zoiper_profile() -> dict:
    PROFILE_JSON.parent.mkdir(parents=True, exist_ok=True)
    host = detect_media_host()
    data = {
        "engine": "freeswitch",
        "sip_host": host,
        "sip_port": FS_PORT,
        "transport": "udp",
        "username": "zoiper",
        "password": "zoiper-lab",
        "dial_number": DEFAULT_DIAL,
        "register": True,
        "codecs": "PCMU,PCMA",
        "stun": "disabled",
        "notes": {
            "avoid_host": "127.0.0.1",
            "avoid_reason": "Docker FreeSWITCH cannot deliver RTP to Mac loopback",
            "p0a": "Dial 7000 after `make freeswitch-zoiper-voice-up` — Vera via CallActor.",
            "p0a_tone_only": "Dial +15550001000 for synthetic P0-A tone gate (no Vera).",
        },
    }
    PROFILE_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def _stack_running() -> bool:
    try:
        out = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(ROOT / "infra" / "freeswitch" / "docker-compose.yml"),
                "ps",
                "--status",
                "running",
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        ).stdout
        return "imvera-freeswitch" in out
    except OSError:
        return False


def main() -> int:
    data = sync_freeswitch_zoiper_profile()
    host = data["sip_host"]
    port = data["sip_port"]

    print("=== IMVERA Zoiper → FreeSWITCH ===\n")
    if not _stack_running():
        print("WARNING: FreeSWITCH stack not running\n")
        print("  Vera on phone:  make freeswitch-zoiper-voice-up")
        print("  P0-A tones:     make freeswitch-up\n")

    print("--- Zoiper account ---")
    print(f"  Domain / Host:  {host}  (port {port} UDP — do not put :5060 in domain field)")
    print("  Transport:      UDP")
    print(f"  Username:       {data['username']}")
    print(f"  Password:       {data['password']}")
    print("  Register:       ON (account must show Registered/green)")
    print("  Codecs:         PCMU + PCMA only (G.711 — P0-A lab)")
    print("  STUN:           OFF (Advanced → Don't use STUN)")
    print("  Disable:        DNS SRV, outbound proxy")
    print("\n--- Dial ---")
    print(f"  {data['dial_number']}  → Vera (after make freeswitch-zoiper-voice-up)")
    print("  +15550001000 → P0-A synthetic gate tones only")
    print("\n--- Vera lab (CallActor) ---")
    print("  make freeswitch-zoiper-voice-up   # MLX + FS + bridge")
    print("  make freeswitch-zoiper-voice-down")
    print("\n--- Auto-apply on macOS ---")
    print("  make freeswitch-zoiper-fix")
    print(f"\nProfile saved: {PROFILE_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
