#!/usr/bin/env python3
"""Patch Zoiper 5 macOS Config.xml — IMVERA lab uses LAN IP:5062 for Docker RTP."""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

from scripts.local_sip_config import load_or_create

ZOIPER_CONFIG = Path.home() / "Library" / "Zoiper5" / "Config.xml"


def _zoiper_running() -> bool:
    try:
        out = subprocess.check_output(["pgrep", "-x", "Zoiper5"], text=True)
        return bool(out.strip())
    except subprocess.CalledProcessError:
        return False


def _quit_zoiper() -> None:
    if not _zoiper_running():
        return
    print("Quitting Zoiper5...")
    subprocess.run(["osascript", "-e", 'quit app "Zoiper5"'], check=False)
    for _ in range(20):
        if not _zoiper_running():
            return
        time.sleep(0.25)
    print("WARN: Zoiper still running — close with Cmd+Q and rerun", file=sys.stderr)


def _patch_config(host: str, port: int, transport: str) -> list[str]:
    if not ZOIPER_CONFIG.exists():
        raise FileNotFoundError(f"Zoiper config not found: {ZOIPER_CONFIG}")

    text = ZOIPER_CONFIG.read_text(encoding="utf-8")
    target_domain = f"{host}:{port}"
    changes: list[str] = []

    new_text, n = re.subn(
        r"(<SIP_domain>)([^<]+)(</SIP_domain>)",
        lambda m: (
            f"{m.group(1)}{target_domain}{m.group(3)}"
            if m.group(2) != target_domain
            else m.group(0)
        ),
        text,
        count=1,
    )
    if n and target_domain not in text:
        changes.append(f"SIP_domain → {target_domain}")

    new_text2, n2 = re.subn(
        r"(<SIP_transport_type>)([^<]+)(</SIP_transport_type>)",
        lambda m: (
            f"{m.group(1)}{transport}{m.group(3)}"
            if m.group(2).lower() != transport.lower()
            else m.group(0)
        ),
        new_text,
        count=1,
    )
    if n2 and f"<SIP_transport_type>{transport}</SIP_transport_type>" not in text:
        changes.append(f"SIP_transport_type → {transport}")

    new_text3, n3 = re.subn(
        r"(<use_stun>)([^<]+)(</use_stun>)",
        r"\1disabled\3",
        new_text2,
        count=0,
    )
    if n3 and "<use_stun>disabled</use_stun>" not in text:
        changes.append("use_stun → disabled (STUN breaks local RTP)")

    if new_text3 != text:
        backup = ZOIPER_CONFIG.with_suffix(".xml.bak-imvera")
        backup.write_text(text, encoding="utf-8")
        ZOIPER_CONFIG.write_text(new_text3, encoding="utf-8")
    elif not changes:
        changes.append("already correct")

    return changes


def main() -> int:
    cfg = load_or_create()
    z = cfg.get("zoiper_setup") or {}
    host = z.get("host") or cfg.get("media_host") or cfg.get("sip_server", "127.0.0.1")
    port = int(cfg.get("port", 5062))
    transport = str(cfg.get("transport", "udp")).lower()

    print(f"IMVERA Zoiper fix: SIP_domain = {host}:{port} ({transport.upper()})")
    print("  (NOT 127.0.0.1 — Docker cannot send RTP to localhost on Mac)")
    print(f"Config: {ZOIPER_CONFIG}")
    _quit_zoiper()
    try:
        changes = _patch_config(host, port, transport)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    for line in changes:
        print(f"  {line}")

    print("\nOpen Zoiper5. STUN must be OFF for local lab (make zoiper-fix sets disabled).")
    print(f"  Username: {cfg['username']}")
    print(f"  Password: {cfg['password']}")
    print(f"  Dial: {cfg.get('vera_extension', '7000')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
