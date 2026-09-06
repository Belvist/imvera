#!/usr/bin/env python3
"""Generate local Zoiper SIP account and sync Asterisk configs."""

from __future__ import annotations

import json
import subprocess

from scripts.local_sip_config import load_or_create

try:
    from packages.voice_runtime.profile import audio_settings
except ImportError:
    audio_settings = None  # type: ignore[assignment,misc]


def _port_conflict_warnings() -> list[str]:
    warnings: list[str] = []
    try:
        out = subprocess.run(
            ["lsof", "-iUDP:5060", "-iUDP:5062", "-iTCP:5060", "-iTCP:5062"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    except OSError:
        return warnings

    if "freeswitc" in out and ":sip" in out:
        warnings.append(
            "FreeSWITCH occupies port 5060 on this Mac. Never use port 5060 in Zoiper."
        )
    if "Zoiper" in out and "freeswitc" in out:
        warnings.append(
            "Zoiper is connected to FreeSWITCH right now (TCP localhost:5060). "
            "Quit Zoiper (Cmd+Q), fix Port=5062, reopen."
        )
    has_asterisk_udp = "5062" in out and "UDP" in out and (
        "com.docke" in out or "docker" in out.lower()
    )
    has_asterisk_tcp = "5062" in out and "TCP" in out and (
        "com.docke" in out or "docker" in out.lower()
    )
    if not has_asterisk_udp:
        warnings.append("Nothing is listening on UDP 5062 — run: make voice-up")
    if not has_asterisk_tcp:
        warnings.append(
            "TCP 5062 not exposed yet — run: make voice-up (recreates Asterisk container)"
        )
    return warnings


def main() -> int:
    data = load_or_create()
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("\nAsterisk configs rendered to config/local/asterisk/")
    print(f"Dial extension {data['vera_extension']} to reach Vera.")

    z = data.get("zoiper_setup") or {}
    host = z.get("host", data.get("media_host", "127.0.0.1"))
    port = z.get("port", data["port"])
    print("\n--- Zoiper account (exact fields) ---")
    print(f"  Domain / Host:  {host}:{port}  (LAN IP — NOT 127.0.0.1, Docker RTP)")
    print(f"  Transport:      UDP")
    print(f"  Username:       {z.get('username', data['username'])}")
    print(f"  Password:       {data['password']}")
    print(f"  Realm (auth):   127.0.0.1  (from Asterisk — leave as-is if asked)")
    print("  Disable:        DNS SRV lookup, outbound proxy")
    if audio_settings:
        audio = audio_settings()
        inject_fmt = audio["inject_format"]
        out_sr = audio["output_sample_rate"]
        print(
            f"  Codec (lab):    Audio settings → enable **L16/{out_sr}** ({inject_fmt}), "
            "move above PCMU/PCMA"
        )
        print("                  Fallback wideband: L16/24000 (slin24) or L16/16000 (slin16)")
    else:
        print("  Codec (lab):    Audio settings → enable **L16/48000** (slin48), move above PCMU/PCMA")
    print("                  If only G.711: audio stays narrowband (8 kHz) — Nokia-phone quality")
    print("  STUN:           Don't use STUN (Advanced) — critical for Docker RTP")
    print("\n--- Why silence on 127.0.0.1 ---")
    print("  Asterisk runs in Docker. Zoiper on 127.0.0.1 → RTP goes to container loopback.")
    print("  PyVoIP e2e uses LAN IP and hears audio. Zoiper must match.")
    print("\n--- Setup ---")
    print("  1. Cmd+Q quit Zoiper")
    print(f"  2. Domain: {host}:{port}")
    print("  3. Or: make zoiper-fix")
    print("  4. In Zoiper Advanced: STUN = Don't use STUN (critical for audio)")
    for warning in _port_conflict_warnings():
        print(f"\n  WARNING: {warning}")
    print("\nIf DNS 503 persists: quit Zoiper fully (Cmd+Q), reopen, disable VPN.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
