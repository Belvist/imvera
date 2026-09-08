#!/usr/bin/env python3
"""FreeSWITCH transport media gate — 440 Hz in / 880 Hz out (no AI stack)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.telephony_gate.evidence import (  # noqa: E402
    MEDIA_GATE_STAMP,
    MediaGateFailure,
    classify_media_gate,
    find_latest_evidence,
    read_evidence,
    write_evidence,
)
from tools.telephony_gate.tone import analyze_duplex_probe  # noqa: E402

GATE_ROOT = ROOT / ".run" / "freeswitch-gate"
REPORT_PATH = GATE_ROOT / "media_gate_report.json"


def _run_unit_tests() -> int:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_freeswitch_bridge.py",
        "tests/test_freeswitch_directional_media.py",
        "tests/test_media_health.py",
        "-q",
    ]
    print("freeswitch-media-gate unit:", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT).returncode


def _write_report(report: dict) -> None:
    GATE_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> int:
    if _run_unit_tests() != 0:
        print("freeswitch-media-gate: unit tests FAILED", file=sys.stderr)
        return 1

    if MEDIA_GATE_STAMP.exists():
        MEDIA_GATE_STAMP.unlink()

    path = find_latest_evidence(GATE_ROOT)
    if path is None:
        report = {
            "status": "unit_only",
            "message": "No live evidence — P0-A: FS tone_stream 880 + mod_audio_stream uplink",
            "next": "make freeswitch-up && python3 services/imvera_media_bridge/main.py && make freeswitch-synthetic-sip",
        }
        _write_report(report)
        print("freeswitch-media-gate: unit OK — live gate NOT RUN (no evidence)")
        return 0

    evidence = read_evidence(path)
    if evidence is None:
        return 1

    failure = MediaGateFailure.UNKNOWN
    inbound_wav = Path(evidence.raw_inbound_wav)
    downlink = Path(evidence.synthetic_downlink_wav)
    if not downlink.is_absolute():
        downlink = ROOT / downlink
    if not inbound_wav.is_absolute():
        inbound_wav = ROOT / inbound_wav
    if inbound_wav.exists() and downlink.exists():
        spectral = analyze_duplex_probe(inbound_wav=inbound_wav, downlink_path=downlink)
        evidence.inbound_has_440_hz = bool(spectral["inbound_has_440_hz"])
        evidence.inbound_has_880_hz = bool(spectral["inbound_has_880_hz"])
        evidence.caller_downlink_has_880_hz = bool(spectral["caller_downlink_has_880_hz"])
        evidence.inbound_440_snr = float(spectral["inbound_440_snr"])
        evidence.inbound_880_snr = float(spectral["inbound_880_snr"])
        evidence.caller_880_snr = float(spectral["caller_880_snr"])

        evidence.gate_phase = "p0a"
        failure = classify_media_gate(evidence, phase="p0a")
    evidence.failure = str(failure)
    write_evidence(path, evidence)

    report = {
        "status": "passed" if failure == MediaGateFailure.PASSED else "failed",
        "failure": str(failure),
        "evidence_path": str(path),
        "call_id": evidence.call_id,
    }
    _write_report(report)

    if failure == MediaGateFailure.PASSED:
        MEDIA_GATE_STAMP.parent.mkdir(parents=True, exist_ok=True)
        MEDIA_GATE_STAMP.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("freeswitch-media-gate: PASSED")
        return 0

    print(f"freeswitch-media-gate: FAIL {failure}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
