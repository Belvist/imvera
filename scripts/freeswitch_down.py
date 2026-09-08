#!/usr/bin/env python3
"""Stop FreeSWITCH stack."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "infra" / "freeswitch" / "docker-compose.yml"


def main() -> int:
    cmd = ["docker", "compose", "-f", str(COMPOSE), "down"]
    print("freeswitch-down:", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
