#!/usr/bin/env python3
"""Zoiper → LiveKit SIP lab profile (replaces Asterisk 7000 path)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZOIPER_JSON = ROOT / "config" / "local" / "zoiper.json"
INBOUND = os.environ.get("LIVEKIT_SIP_INBOUND_NUMBER", "+15550001000")


def _sync_livekit_profile() -> dict:
    from scripts.local_sip_config import detect_media_host, load_or_create

    data = load_or_create()
    host = detect_media_host()
    port = 5065 if sys.platform == "darwin" else 5060
    data["telephony_mode"] = "livekit"
    data["livekit"] = {
        "sip_host": host,
        "sip_port": port,
        "dial_number": INBOUND,
        "transport": "UDP",
        "codec": "PCMU",
        "registration_required": False,
        "note": "Call dial_number — LiveKit SIP inbound trunk (no Asterisk 7000)",
    }
    data["zoiper_livekit"] = {
        "host": host,
        "port": port,
        "domain": f"{host}:{port}",
        "transport": "UDP",
        "username": "livekit-lab",
        "password": "",
        "dial": INBOUND,
        "disable_dns_srv": True,
        "codec": "PCMU only (disable G.722 for LiveKit SIP lab)",
        "avoid_asterisk": "Do NOT use :5062 / extension 7000 — that is the old Asterisk path",
    }
    ZOIPER_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def _port_check(host: str, port: int) -> bool:
    try:
        out = subprocess.run(
            ["lsof", "-iTCP", f":{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        return str(port) in out
    except OSError:
        return False


def main() -> int:
    data = _sync_livekit_profile()
    lk = data["livekit"]
    z = data["zoiper_livekit"]
    host, port = lk["sip_host"], lk["sip_port"]

    print("=== IMVERA Zoiper → LiveKit (NOT Asterisk) ===\n")
    print(f"  SIP host:port     {host}:{port}")
    print(f"  Dial number:      {lk['dial_number']}")
    print(f"  Registration:     OFF — LiveKit returns 405 on REGISTER")
    print(f"  Account status:   grey/offline is OK — dial without registering")
    print(f"  Codec:            PCMU / G.711 μ-law")
    print(f"  Old Asterisk path: {z['avoid_asterisk']}\n")

    print("--- Zoiper account ---")
    print(f"  1. Cmd+Q quit Zoiper")
    print(f"  2. New account OR edit existing:")
    print(f"     Domain / Host:  {z['domain']}")
    print(f"     Username:       {z['username']}  (any label — trunk does not auth in lab)")
    print(f"     Password:       (empty)")
    print(f"     Transport:      UDP")
    print("     Advanced → disable DNS SRV")
    print("     Codecs: enable PCMU only; disable G.722")
    print(f"  3. Call: {lk['dial_number']}")
    print("     Or URI: sip:{number}@{host}:{port}\n")

    print("--- Stack (before call) ---")
    print("  make livekit-up")
    print("  make livekit-setup-sip")
    print("  voice gateway running on :9200 (unset IMVERA_LIVEKIT_MEDIA_GATE for full Vera)")
    print("  STT/TTS/LLM up (make voice-up or models-up)\n")

    if not _port_check("127.0.0.1", 7880):
        print("  WARNING: LiveKit API :7880 not listening — run: make livekit-up")
    if not _port_check("127.0.0.1", port):
        print(f"  WARNING: LiveKit SIP :{port} not listening — run: make livekit-up")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
