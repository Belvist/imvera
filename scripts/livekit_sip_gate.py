#!/usr/bin/env python3
"""LiveKit SIP local gate — adapter contract + optional live stack."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    unit_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_livekit_outbound.py",
        "tests/test_livekit_supervisor.py",
        "tests/test_livekit_session_contract.py",
        "tests/test_livekit_privacy.py",
        "tests/test_livekit_readiness.py",
        "-q",
    ]
    print("livekit-sip-gate unit:", " ".join(unit_cmd))
    unit = subprocess.run(unit_cmd, cwd=ROOT)
    if unit.returncode != 0:
        print("livekit-sip-gate: unit tests FAILED", file=sys.stderr)
        return unit.returncode

    health = subprocess.run([sys.executable, str(ROOT / "scripts" / "livekit_health.py")])
    if health.returncode != 0:
        print(
            "livekit-sip-gate: live stack NOT RUNNING — unit tests passed, "
            "start with: make livekit-up && make livekit-setup-sip",
            file=sys.stderr,
        )
        return 0 if os.environ.get("IMVERA_LIVEKIT_GATE_REQUIRE_STACK", "0") != "1" else 1

    live_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_livekit_sip_live.py",
        "-q",
        "-m",
        "livekit_live",
    ]
    print("livekit-sip-gate live:", " ".join(live_cmd))
    live = subprocess.run(live_cmd, cwd=ROOT)
    if live.returncode != 0:
        print("livekit-sip-gate: live integration FAILED", file=sys.stderr)
        return live.returncode

    print("livekit-sip-gate: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
