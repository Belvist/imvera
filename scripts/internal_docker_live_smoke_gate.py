#!/usr/bin/env python3
"""Host orchestrator for Phase A internal docker live smoke (1 call default)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "infra" / "freeswitch" / "docker-compose.yml"
VOICE_OVERLAY = ROOT / "infra" / "freeswitch" / "docker-compose.zoiper-voice.yml"
BRIDGE_URL = "http://127.0.0.1:9210/health/ready"


def _run(cmd: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> int:
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, env=env)
    if check and proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return proc.returncode


def _compose_cmd(*args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(COMPOSE),
        "-f",
        str(VOICE_OVERLAY),
        *args,
    ]


def _git_image_tag() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "local"


def _wait_bridge(timeout_s: float = 120.0) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BRIDGE_URL, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(1.5)
    return False


def main() -> int:
    calls = os.environ.get("IMVERA_INTERNAL_DOCKER_CALLS", "1")
    scenario = os.environ.get("IMVERA_LIVE_DEBUG_SCENARIO", "good-clean_short-00")

    print("=== Phase A: internal docker live smoke (diagnostic) ===", flush=True)
    print("Ensuring MLX workers + CallActor bridge...", flush=True)
    rc = _run(
        [sys.executable, str(ROOT / "scripts" / "freeswitch_zoiper_voice_up.py")], check=False
    )
    if rc != 0:
        print("BLOCKED: freeswitch-zoiper-voice-up failed", file=sys.stderr)
        return rc

    if not _wait_bridge():
        print("BLOCKED: media-bridge not ready", file=sys.stderr)
        return 1

    manifest = ROOT / "tests" / "assets" / "blackbox_voice" / "manifest.json"
    if not manifest.is_file():
        print("BLOCKED: run make blackbox-synthesize-vera first", file=sys.stderr)
        return 1

    compose_env = os.environ.copy()
    compose_env["IMVERA_FS_IMAGE_TAG"] = _git_image_tag()
    compose_env["IMVERA_INTERNAL_DOCKER_CALLS"] = calls
    compose_env["IMVERA_LIVE_DEBUG_SCENARIO"] = scenario

    return _run(
        _compose_cmd(
            "--profile",
            "internal-smoke",
            "run",
            "--rm",
            "--no-deps",
            "internal-blackbox-gate",
        ),
        check=False,
        env=compose_env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
