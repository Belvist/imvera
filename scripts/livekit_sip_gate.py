#!/usr/bin/env python3
"""LiveKit SIP AI gate — full stack after media-gate PASS."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from packages.telephony.livekit_gate_evidence import MEDIA_GATE_STAMP  # noqa: E402


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
        "tests/test_livekit_gate_evidence.py",
        "-q",
    ]
    print("livekit-sip-gate unit:", " ".join(unit_cmd))
    unit = subprocess.run(unit_cmd, cwd=ROOT)
    if unit.returncode != 0:
        print("livekit-sip-gate: unit tests FAILED", file=sys.stderr)
        return unit.returncode

    require_live = os.environ.get("IMVERA_LIVEKIT_GATE_REQUIRE_STACK", "0") == "1"
    if require_live and not MEDIA_GATE_STAMP.exists():
        print(
            "livekit-sip-gate: BLOCKED — run make livekit-media-gate first "
            f"(missing {MEDIA_GATE_STAMP})",
            file=sys.stderr,
        )
        return 1
    if MEDIA_GATE_STAMP.exists():
        stamp = json.loads(MEDIA_GATE_STAMP.read_text(encoding="utf-8"))
        print(f"livekit-sip-gate: media gate stamp OK passed_at={stamp.get('passed_at')}")

    health_cmd = [sys.executable, str(ROOT / "scripts" / "livekit_health.py"), "--mode", "ai"]
    print("livekit-sip-gate ai-health:", " ".join(health_cmd))
    health = subprocess.run(health_cmd, cwd=ROOT)
    if health.returncode != 0:
        if require_live:
            print("livekit-sip-gate: AI stack health FAILED", file=sys.stderr)
            return health.returncode
        print(
            "livekit-sip-gate: AI stack NOT RUNNING — unit tests passed only",
            file=sys.stderr,
        )
        return 0

    live_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_livekit_sip_live.py",
        "tests/test_livekit_media_live.py",
        "-q",
        "-m",
        "livekit_live or livekit_media_live",
    ]
    print("livekit-sip-gate live:", " ".join(live_cmd))
    live = subprocess.run(live_cmd, cwd=ROOT)
    if live.returncode != 0:
        print("livekit-sip-gate: live integration FAILED", file=sys.stderr)
        return live.returncode

    print("livekit-sip-gate: PASSED (unit + AI health + live probes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
