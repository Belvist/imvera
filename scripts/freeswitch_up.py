#!/usr/bin/env python3
"""Start FreeSWITCH production telephony stack (ADR-013)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "infra" / "freeswitch" / "docker-compose.yml"


def _git_image_tag() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "local"


def main() -> int:
    if not COMPOSE.exists():
        print(f"freeswitch-up: missing {COMPOSE}", file=sys.stderr)
        return 1
    env = os.environ.copy()
    env["IMVERA_FS_IMAGE_TAG"] = _git_image_tag()
    cmd = ["docker", "compose", "-f", str(COMPOSE), "up", "-d", "--build"]
    print("freeswitch-up:", " ".join(cmd), f"(image tag={env['IMVERA_FS_IMAGE_TAG']})")
    rc = subprocess.run(cmd, cwd=ROOT, env=env).returncode
    if rc != 0:
        return rc
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "freeswitch_readiness_check.py"), "--wait", "120"],
        cwd=ROOT,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
