#!/usr/bin/env python3
"""Generate local Zoiper SIP account and sync Asterisk configs."""

from __future__ import annotations

import json
import sys

from scripts.local_sip_config import load_or_create


def main() -> int:
    data = load_or_create()
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("\nAsterisk configs rendered to config/local/asterisk/")
    print(f"Dial extension {data['vera_extension']} to reach Vera.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
