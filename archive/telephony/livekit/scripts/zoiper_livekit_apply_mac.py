#!/usr/bin/env python3
"""Patch Zoiper 5 macOS — LiveKit SIP lab (no REGISTER, PCMU, :5065)."""

from __future__ import annotations

import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.zoiper_livekit_info import _sync_livekit_profile

ZOIPER_CONFIG = Path.home() / "Library" / "Zoiper5" / "Config.xml"
CODEC_PCMU = "0"
CODEC_G722 = "7"
NARROWBAND_ENABLE = {CODEC_PCMU, "6"}  # PCMU, PCMA
NARROWBAND_DISABLE_OTHERS = {"1", "16"}  # GSM, G.729


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


def _set_text(parent: ET.Element, tag: str, value: str) -> bool:
    el = parent.find(tag)
    if el is None:
        el = ET.SubElement(parent, tag)
    if el.text == value:
        return False
    el.text = value
    return True


def _patch_account_codecs(account: ET.Element) -> list[str]:
    changes: list[str] = []
    codecs = account.find("codecs")
    if codecs is None:
        return changes
    for codec in codecs.findall("codec"):
        cid_el = codec.find("codec_id")
        if cid_el is None or cid_el.text is None:
            continue
        cid = cid_el.text.strip()
        enabled_el = codec.find("enabled")
        priority_el = codec.find("priority")
        if cid == CODEC_PCMU:
            if enabled_el is not None and enabled_el.text != "true":
                enabled_el.text = "true"
                changes.append("enabled PCMU (codec_id=0)")
            if priority_el is not None and priority_el.text != "1":
                priority_el.text = "1"
                changes.append("PCMU priority → 1")
        elif cid == CODEC_G722:
            if enabled_el is not None and enabled_el.text != "false":
                enabled_el.text = "false"
                changes.append("disabled G.722 (LiveKit SIP lab uses G.711)")
        elif cid in NARROWBAND_DISABLE_OTHERS:
            if enabled_el is not None and enabled_el.text != "false":
                enabled_el.text = "false"
                changes.append(f"disabled codec_id={cid}")
    return changes


def _patch_config(host: str, port: int, dial: str) -> list[str]:
    if not ZOIPER_CONFIG.exists():
        raise FileNotFoundError(f"Zoiper config not found: {ZOIPER_CONFIG}")

    text = ZOIPER_CONFIG.read_text(encoding="utf-8")
    backup = ZOIPER_CONFIG.with_suffix(".xml.bak-livekit")
    backup.write_text(text, encoding="utf-8")

    root = ET.fromstring(text)
    changes: list[str] = []
    target_domain = f"{host}:{port}"
    account_name = f"livekit@{host}"

    accounts = root.find("accounts")
    if accounts is None:
        raise RuntimeError("No <accounts> in Zoiper Config.xml")

    account = accounts.find("account")
    if account is None:
        raise RuntimeError("No <account> in Zoiper Config.xml")

    if _set_text(account, "name", account_name):
        changes.append(f"name → {account_name}")
    if _set_text(account, "username", "livekit-lab"):
        changes.append("username → livekit-lab")
    if _set_text(account, "password", ""):
        changes.append("password cleared (no SIP auth in lab trunk)")
    if _set_text(account, "register_on_startup", "false"):
        changes.append("register_on_startup → false (LiveKit rejects REGISTER → 405)")
    if _set_text(account, "mwi_subscribe_usage", "none"):
        changes.append("mwi_subscribe_usage → none")
    if _set_text(account, "SIP_domain", target_domain):
        changes.append(f"SIP_domain → {target_domain}")
    if _set_text(account, "SIP_transport_type", "udp"):
        changes.append("SIP_transport_type → udp")
    if _set_text(account, "SIP_use_auth_username", "false"):
        changes.append("SIP_use_auth_username → false")
    changes.extend(_patch_account_codecs(account))

    new_body = ET.tostring(root, encoding="unicode")
    if text.startswith("<?xml"):
        header, _, _ = text.partition(">")
        sep = "\n" if "\n" in text[:120] else ""
        out = f"{header}>{sep}{new_body}"
    else:
        out = new_body
    ZOIPER_CONFIG.write_text(out, encoding="utf-8")

    if not changes:
        changes.append("already patched for LiveKit")
    changes.append(f"backup → {backup}")
    changes.append(f"dial → {dial}")
    return changes


def main() -> int:
    data = _sync_livekit_profile()
    lk = data["livekit"]
    host = str(lk["sip_host"])
    port = int(lk["sip_port"])
    dial = str(lk["dial_number"])

    print(f"IMVERA Zoiper LiveKit fix: {host}:{port} (NO REGISTER)")
    print("  LiveKit SIP inbound accepts INVITE only — REGISTER returns 405")
    _quit_zoiper()
    try:
        changes = _patch_config(host, port, dial)
    except (FileNotFoundError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        return 1

    for line in changes:
        print(f"  {line}")

    print("\nOpen Zoiper5 — account should show offline/grey (no registration). That is OK.")
    print(f"Dial manually: {dial}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
