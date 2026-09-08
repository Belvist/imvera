#!/usr/bin/env python3
"""Health check for self-hosted LiveKit — per-component, media vs AI modes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.livekit_health_common import run_checks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="LiveKit stack health")
    parser.add_argument(
        "--mode",
        choices=("media", "ai", "all"),
        default="all",
        help="media=transport only; ai=inference only; all=both",
    )
    args = parser.parse_args()

    checks = run_checks(args.mode)
    failed = []
    for name, ok, detail in checks:
        print(f"  {'OK' if ok else 'FAIL':4} {name:18} {detail}")
        if not ok:
            failed.append(name)

    label = f"livekit-health ({args.mode})"
    if failed:
        print(f"{label}: FAILED — {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"{label}: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
