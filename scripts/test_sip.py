#!/usr/bin/env python3
"""SIP lab gate — ARI registration + optional originate smoke."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx

from packages.telephony.asterisk import is_stasis_app_registered, normalize_ari_http_root

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    code = subprocess.call([sys.executable, str(ROOT / "scripts" / "voice_doctor.py")])
    if code != 0:
        print(
            "BLOCKED: run make voice-up first (STT/TTS/LLM/gateway/asterisk_app/Asterisk)",
            file=sys.stderr,
        )
        return code

    from scripts.local_sip_config import load_or_create

    cfg = load_or_create()
    auth = (cfg["ari_user"], cfg["ari_password"])
    http_root = normalize_ari_http_root("http://127.0.0.1:8088")
    if not is_stasis_app_registered(http_root, auth, cfg["stasis_app"]):
        print("BLOCKED: Stasis app not registered", file=sys.stderr)
        return 1

    try:
        r = httpx.get(f"{http_root}/ari/asterisk/info", auth=auth, timeout=3.0)
        if r.status_code != 200:
            print(f"BLOCKED: Asterisk info HTTP {r.status_code}", file=sys.stderr)
            return 1
        info = r.json()
        print(f"  Asterisk: {info.get('system_name', 'unknown')} / {info.get('version', '?')}")
    except httpx.HTTPError as exc:
        print(f"BLOCKED: cannot query Asterisk info: {exc}", file=sys.stderr)
        return 1

    print("test-sip: lab SIP prerequisites OK — dial 7000 from Zoiper for live audio proof")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
