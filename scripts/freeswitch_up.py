#!/usr/bin/env python3
"""Start FreeSWITCH production telephony stack (ADR-013)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "infra" / "freeswitch" / "docker-compose.yml"


def main() -> int:
    if not COMPOSE.exists():
        print(f"freeswitch-up: missing {COMPOSE}", file=sys.stderr)
        return 1
    cmd = ["docker", "compose", "-f", str(COMPOSE), "up", "-d", "--build"]
    print("freeswitch-up:", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
