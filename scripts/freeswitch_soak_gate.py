#!/usr/bin/env python3
"""FreeSWITCH P0-A soak gate — 1 / 10 / 100 transport calls (no AI)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.telephony_gate.evidence import (  # noqa: E402
    MEDIA_GATE_STAMP,
    MediaGateFailure,
    classify_media_gate,
    read_evidence,
    write_evidence,
)
from tools.telephony_gate.tone import analyze_duplex_probe  # noqa: E402

GATE_ROOT = ROOT / ".run" / "freeswitch-gate"
REPORT_PATH = GATE_ROOT / "p0a_soak_report.json"


def _run_synthetic(calls: int) -> int:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "freeswitch_synthetic_sip_media.py"),
        "--calls",
        str(calls),
    ]
    print("freeswitch-soak:", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT).returncode


def _classify_latest() -> tuple[MediaGateFailure, dict]:
    paths = sorted(GATE_ROOT.glob("*/media_gate_evidence.json"), key=lambda p: p.stat().st_mtime)
    if not paths:
        return MediaGateFailure.UNKNOWN, {}
    path = paths[-1]
    evidence = read_evidence(path)
    if evidence is None:
        return MediaGateFailure.UNKNOWN, {}
    inbound_wav = Path(evidence.raw_inbound_wav)
    downlink = Path(evidence.synthetic_downlink_wav)
    if inbound_wav.exists() and downlink.exists():
        spectral = analyze_duplex_probe(inbound_wav=inbound_wav, downlink_path=downlink)
        evidence.inbound_has_440_hz = bool(spectral["inbound_has_440_hz"])
        evidence.inbound_has_880_hz = bool(spectral["inbound_has_880_hz"])
        evidence.caller_downlink_has_880_hz = bool(spectral["caller_downlink_has_880_hz"])
        evidence.gate_phase = "p0a"
    failure = classify_media_gate(evidence, phase="p0a")
    evidence.failure = str(failure)
    write_evidence(path, evidence)
    return failure, evidence.to_dict()


def main() -> int:
    parser = argparse.ArgumentParser(description="FreeSWITCH P0-A soak gate")
    parser.add_argument(
        "--calls", type=int, default=int(os.environ.get("IMVERA_FS_SOAK_CALLS", "1"))
    )
    args = parser.parse_args()

    unit = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "freeswitch_media_gate.py")],
        cwd=ROOT,
    )
    if unit.returncode != 0:
        return 1

    require_live = os.environ.get("IMVERA_FS_GATE_REQUIRE_STACK", "0") == "1"
    if not require_live:
        print("freeswitch-soak: unit OK — set IMVERA_FS_GATE_REQUIRE_STACK=1 for live soak")
        return 0

    if MEDIA_GATE_STAMP.exists():
        MEDIA_GATE_STAMP.unlink()

    if _run_synthetic(args.calls) != 0:
        return 1
    time.sleep(1.0)
    failure, evidence = _classify_latest()
    report = {
        "gate": "p0a",
        "calls": args.calls,
        "failure": str(failure),
        "evidence": evidence,
        "passed": failure == MediaGateFailure.PASSED,
    }
    GATE_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if failure != MediaGateFailure.PASSED:
        print(f"freeswitch-soak: FAIL {failure}", file=sys.stderr)
        return 1

    if args.calls >= 100:
        MEDIA_GATE_STAMP.parent.mkdir(parents=True, exist_ok=True)
        MEDIA_GATE_STAMP.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"freeswitch-soak: P0-A PASSED calls={args.calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
