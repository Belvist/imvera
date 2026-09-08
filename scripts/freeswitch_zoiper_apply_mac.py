#!/usr/bin/env python3
"""Patch Zoiper 5 macOS — FreeSWITCH P0-A (REGISTER, PCMU, :5060, LAN IP)."""

from __future__ import annotations

import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.freeswitch_zoiper_info import sync_freeswitch_zoiper_profile

ZOIPER_CONFIG = Path.home() / "Library" / "Zoiper5" / "Config.xml"
CODEC_PCMU = "0"
CODEC_PCMA = "6"
CODEC_G722 = "7"
NARROWBAND_ENABLE = {CODEC_PCMU, CODEC_PCMA}
NARROWBAND_DISABLE = {"1", "16", CODEC_G722}


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
        if cid in NARROWBAND_ENABLE:
            if enabled_el is not None and enabled_el.text != "true":
                enabled_el.text = "true"
                changes.append(f"enabled codec_id={cid} (G.711)")
            if priority_el is not None and cid == CODEC_PCMU and priority_el.text != "1":
                priority_el.text = "1"
                changes.append("PCMU priority → 1")
        elif cid in NARROWBAND_DISABLE:
            if enabled_el is not None and enabled_el.text != "false":
                enabled_el.text = "false"
                changes.append(f"disabled codec_id={cid}")
    return changes


def _patch_config(host: str, port: int, username: str, password: str, dial: str) -> list[str]:
    if not ZOIPER_CONFIG.exists():
        raise FileNotFoundError(f"Zoiper config not found: {ZOIPER_CONFIG}")

    text = ZOIPER_CONFIG.read_text(encoding="utf-8")
    backup = ZOIPER_CONFIG.with_suffix(".xml.bak-freeswitch")
    backup.write_text(text, encoding="utf-8")

    root = ET.fromstring(text)
    changes: list[str] = []
    target_domain = host
    account_name = f"{username}@{host}"

    accounts = root.find("accounts")
    if accounts is None:
        raise RuntimeError("No <accounts> in Zoiper Config.xml")

    account = accounts.find("account")
    if account is None:
        raise RuntimeError("No <account> in Zoiper Config.xml — add one account in Zoiper UI first")

    if _set_text(account, "name", account_name):
        changes.append(f"name → {account_name}")
    if _set_text(account, "username", username):
        changes.append(f"username → {username}")
    if _set_text(account, "password", password):
        changes.append("password updated")
    if _set_text(account, "register_on_startup", "true"):
        changes.append("register_on_startup → true")
    if _set_text(account, "mwi_subscribe_usage", "none"):
        changes.append("mwi_subscribe_usage → none")
    if _set_text(account, "SIP_domain", target_domain):
        changes.append(f"SIP_domain → {target_domain}")
    if _set_text(account, "mwi_subscribe_usage", "none"):
        changes.append("mwi_subscribe_usage → none")
    if _set_text(account, "use_number_rewriting", "false"):
        changes.append("use_number_rewriting → false")
    if _set_text(account, "SIP_transport_type", "udp"):
        changes.append("SIP_transport_type → udp")
    if _set_text(account, "SIP_use_auth_username", "true"):
        changes.append("SIP_use_auth_username → true")
    if _set_text(account, "SIP_auth_username", username):
        changes.append("SIP_auth_username set")
    changes.extend(_patch_account_codecs(account))

    use_stun = root.find(".//use_stun")
    if use_stun is not None and use_stun.text != "disabled":
        use_stun.text = "disabled"
        changes.append("use_stun → disabled")

    sip_options = root.find("sip_options")
    if sip_options is not None:
        port_el = sip_options.find("port")
        if port_el is not None and port_el.text != "5070":
            port_el.text = "5070"
            changes.append("sip_options.port → 5070 (Docker owns host :5060)")
        random_el = sip_options.find("use_random_port")
        if random_el is not None and random_el.text != "true":
            random_el.text = "true"
            changes.append("sip_options.use_random_port → true")

    new_body = ET.tostring(root, encoding="unicode")
    if text.startswith("<?xml"):
        header, _, _ = text.partition(">")
        sep = "\n" if "\n" in text[:120] else ""
        out = f"{header}>{sep}{new_body}"
    else:
        out = new_body
    ZOIPER_CONFIG.write_text(out, encoding="utf-8")

    if not changes:
        changes.append("already patched for FreeSWITCH")
    changes.append(f"backup → {backup}")
    changes.append(f"dial → {dial}")
    return changes


def main() -> int:
    data = sync_freeswitch_zoiper_profile()
    host = str(data["sip_host"])
    port = int(data["sip_port"])
    username = str(data["username"])
    password = str(data["password"])
    dial = str(data["dial_number"])

    print(f"IMVERA Zoiper FreeSWITCH fix: {username}@{host}:{port} (REGISTER)")
    print("  Domain must be LAN IP — NOT 127.0.0.1 (Docker RTP)")
    _quit_zoiper()
    try:
        changes = _patch_config(host, port, username, password, dial)
    except (FileNotFoundError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        return 1

    for line in changes:
        print(f"  {line}")

    print("\nOpen Zoiper5 — account should register (green).")
    print(f"Dial: {dial}  (P0-A: 880 Hz tone test)")
    print("Stack: make freeswitch-up  |  gate: make freeswitch-docker-gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
