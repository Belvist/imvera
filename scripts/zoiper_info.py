#!/usr/bin/env python3
"""Generate local Zoiper SIP account credentials."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "config" / "local" / "zoiper.json"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        data = json.loads(OUT.read_text())
    else:
        data = {
            "sip_server": "127.0.0.1",
            "transport": "UDP",
            "port": 5060,
            "username": "1001",
            "password": secrets.token_urlsafe(12),
            "vera_extension": "7000",
        }
        OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\nSaved to {OUT}")
    print("Dial extension 7000 to reach Vera.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
