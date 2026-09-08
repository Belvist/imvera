#!/usr/bin/env python3
"""Stop self-hosted LiveKit stack."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
from scripts.livekit_compose import livekit_compose_file  # noqa: E402

COMPOSE = livekit_compose_file()


def main() -> int:
    cmd = ["docker", "compose", "-f", str(COMPOSE), "down"]
    print("livekit-down:", " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
