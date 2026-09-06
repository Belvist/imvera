#!/usr/bin/env python3
"""Automated voice path smoke — fails unless stack responds."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    code = subprocess.call([sys.executable, str(ROOT / "scripts" / "voice_doctor.py")])
    if code != 0:
        return code
    try:
        r = httpx.get("http://127.0.0.1:9200/health/ready", timeout=3.0)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"BLOCKED: gateway smoke failed: {exc}", file=sys.stderr)
        return 1
    print("voice-e2e: stack healthy — place Zoiper call to extension 7000 for live proof")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
