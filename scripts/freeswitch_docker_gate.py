#!/usr/bin/env python3
"""Run FreeSWITCH P0-A gate fully in Docker (bridge + FS + synthetic caller)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "infra" / "freeswitch" / "docker-compose.yml"
GATE_ROOT = ROOT / ".run" / "freeswitch-gate"
BRIDGE_HEALTH = "http://127.0.0.1:9210/health/ready"


def _run(cmd: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> int:
    print("+", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, env=env)
    if check and proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return proc.returncode


def _wait_bridge(timeout_s: float = 90.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BRIDGE_HEALTH, timeout=2) as resp:
                if resp.status == 200:
                    print("freeswitch-docker-gate: media-bridge ready")
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(2)
    print("freeswitch-docker-gate: media-bridge health timeout", file=sys.stderr)
    raise SystemExit(1)


def _git_image_tag() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "local"


def _wait_fs_module(timeout_s: float = 90.0) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "freeswitch_readiness_check.py"),
            "--wait",
            str(int(timeout_s)),
        ],
        cwd=ROOT,
        check=False,
    )
    if proc.returncode != 0:
        print(
            "freeswitch-docker-gate: FREESWITCH NOT READY reason=MOD_AUDIO_STREAM_MISSING",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print("freeswitch-docker-gate: mod_audio_stream ready")


def _clear_gate_artifacts() -> None:
    GATE_ROOT.mkdir(parents=True, exist_ok=True)
    for child in GATE_ROOT.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def main() -> int:
    if shutil.which("docker") is None:
        print("freeswitch-docker-gate: docker not found", file=sys.stderr)
        return 1

    _clear_gate_artifacts()

    compose_env = os.environ.copy()
    compose_env["IMVERA_FS_IMAGE_TAG"] = _git_image_tag()

    _run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE),
            "up",
            "-d",
            "--build",
            "media-bridge",
            "freeswitch",
        ],
        env=compose_env,
    )
    _wait_bridge()
    time.sleep(15)
    _wait_fs_module()

    rc = _run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE),
            "--profile",
            "gate",
            "run",
            "--rm",
            "synthetic-gate",
        ],
        check=False,
    )
    if rc != 0:
        print("freeswitch-docker-gate: synthetic caller FAILED", file=sys.stderr)
        return rc

    time.sleep(2)
    rc = _run([sys.executable, str(ROOT / "scripts" / "freeswitch_media_gate.py")], check=False)
    report_path = GATE_ROOT / "media_gate_report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        print("freeswitch-docker-gate report:", json.dumps(report, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
