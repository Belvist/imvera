#!/usr/bin/env python3
"""Fail-fast FreeSWITCH readiness — mod_audio_stream must be loaded."""

from __future__ import annotations

import argparse

from packages.telephony.freeswitch_readiness import (
    check_freeswitch_ready,
    wait_freeswitch_ready,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="FreeSWITCH readiness gate")
    parser.add_argument("--container", default="imvera-freeswitch")
    parser.add_argument("--wait", type=float, default=0.0, help="Poll until ready (seconds)")
    args = parser.parse_args()

    if args.wait > 0:
        result = wait_freeswitch_ready(container=args.container, timeout_s=args.wait)
    else:
        result = check_freeswitch_ready(container=args.container)

    print(result.message())
    if result.modules:
        for name, loaded in result.modules.items():
            print(f"  {name}: {'loaded' if loaded else 'MISSING'}")
    return 0 if result.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
