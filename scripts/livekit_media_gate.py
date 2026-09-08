#!/usr/bin/env python3
"""LiveKit transport media gate — SIP → RTP → LiveKit → IMVERA PCM (no AI stack)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from packages.telephony.livekit_gate_evidence import (  # noqa: E402
    MEDIA_GATE_STAMP,
    MediaGateFailure,
    classify_media_gate,
    find_latest_evidence,
    read_evidence,
    write_evidence,
)
from scripts.livekit_health_common import run_checks  # noqa: E402

GATE_ROOT = ROOT / ".run" / "livekit-gate"
REPORT_PATH = GATE_ROOT / "media_gate_report.json"
GATEWAY = os.environ.get("IMVERA_VOICE_GATEWAY_HTTP", "http://127.0.0.1:9200")
WAIT_EVIDENCE_S = float(os.environ.get("IMVERA_LIVEKIT_MEDIA_GATE_WAIT_S", "90"))


def _run_unit_tests() -> int:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_livekit_gate_evidence.py",
        "tests/test_livekit_outbound.py",
        "tests/test_livekit_supervisor.py",
        "tests/test_livekit_session_contract.py",
        "tests/test_livekit_privacy.py",
        "tests/test_livekit_readiness.py",
        "-q",
    ]
    print("livekit-media-gate unit:", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT).returncode


def _check_media_health() -> tuple[bool, list[str]]:
    checks = run_checks("media")
    failed = []
    for name, ok, detail in checks:
        print(f"  {'OK' if ok else 'FAIL':4} {name:18} {detail}")
        if not ok:
            failed.append(name)
    return not failed, failed


def _check_gateway_media_gate() -> tuple[bool, str]:
    import httpx

    try:
        r = httpx.get(f"{GATEWAY}/health/ready", timeout=3.0)
    except httpx.HTTPError as exc:
        return False, f"gateway unreachable: {exc}"
    if r.status_code not in {200, 503}:
        return False, f"gateway HTTP {r.status_code}"
    if os.environ.get("IMVERA_LIVEKIT_MEDIA_GATE") != "1":
        return (
            False,
            "set IMVERA_LIVEKIT_MEDIA_GATE=1 on voice gateway before media gate",
        )
    return True, f"{GATEWAY} up (media_gate env set)"


def _maybe_start_pcap() -> subprocess.Popen | None:
    if os.environ.get("IMVERA_LIVEKIT_GATE_PCAP") != "1":
        return None
    GATE_ROOT.mkdir(parents=True, exist_ok=True)
    pcap = GATE_ROOT / "media_gate.pcap"
    cmd = [
        "tcpdump",
        "-i",
        "any",
        "-w",
        str(pcap),
        "port",
        "5060",
        "or",
        "udp",
        "portrange",
        "10000-20000",
        "or",
        "udp",
        "port",
        "7882",
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"livekit-media-gate: pcap → {pcap}")
        return proc
    except FileNotFoundError:
        print("livekit-media-gate: tcpdump not found — skipping pcap", file=sys.stderr)
        return None


def _run_synthetic_sip() -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / "livekit_synthetic_sip_media.py")]
    print("livekit-media-gate synthetic:", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT).returncode


def _wait_for_evidence(since_ts: float) -> Path | None:
    deadline = time.time() + WAIT_EVIDENCE_S
    while time.time() < deadline:
        path = find_latest_evidence(GATE_ROOT)
        if path and path.stat().st_mtime >= since_ts - 1.0:
            evidence = read_evidence(path)
            if evidence and evidence.actor_pcm_frames > 0:
                return path
        time.sleep(0.5)
    return find_latest_evidence(GATE_ROOT)


def _failure_boundary(failure: MediaGateFailure) -> str:
    mapping = {
        MediaGateFailure.SIP_NO_RTP: "INVITE ok, RTP=0 → SIP endpoint/network/SDP",
        MediaGateFailure.SIP_NO_TRACK: "RTP>0, no SIP participant track → LiveKit SIP media",
        MediaGateFailure.NO_AUDIOSTREAM: "track exists, AudioStream frames=0 → LiveKit RTC/subscription",
        MediaGateFailure.ADAPTER_DROP: "AudioStream>0, actor frames=0 → LiveKitTelephonyAdapter",
        MediaGateFailure.NO_NONZERO_PCM: "actor frames>0 but silence → remote_silence",
        MediaGateFailure.VERA_IN_INBOUND: "directional violation — Vera in inbound",
        MediaGateFailure.PASSED: "transport P0 PASSED",
        MediaGateFailure.UNKNOWN: "unclassified",
    }
    return mapping.get(failure, failure.value)


def _write_report(report: dict) -> None:
    GATE_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> int:
    if _run_unit_tests() != 0:
        print("livekit-media-gate: unit tests FAILED", file=sys.stderr)
        return 1

    ok, failed = _check_media_health()
    if not ok:
        print(f"livekit-media-gate: health FAILED — {', '.join(failed)}", file=sys.stderr)
        return 1

    gw_ok, gw_detail = _check_gateway_media_gate()
    print(f"  {'OK' if gw_ok else 'FAIL':4} gateway_media_gate {gw_detail}")
    require_live = os.environ.get("IMVERA_LIVEKIT_GATE_REQUIRE_STACK", "0") == "1"
    if not gw_ok:
        if require_live:
            return 1
        print(
            "livekit-media-gate: live stack NOT RUNNING — unit tests passed only",
            file=sys.stderr,
        )
        return 0

    if MEDIA_GATE_STAMP.exists():
        MEDIA_GATE_STAMP.unlink()

    pcap_proc = _maybe_start_pcap()
    since_ts = time.time()
    synth_rc = _run_synthetic_sip()
    if pcap_proc is not None:
        pcap_proc.terminate()
        try:
            pcap_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pcap_proc.kill()

    if synth_rc != 0:
        print("livekit-media-gate: synthetic SIP FAILED", file=sys.stderr)
        return 1

    evidence_path = _wait_for_evidence(since_ts)
    if evidence_path is None:
        report = {
            "status": "fail",
            "failure": str(MediaGateFailure.UNKNOWN),
            "failure_boundary": _failure_boundary(MediaGateFailure.UNKNOWN),
            "reason": "no media_gate_evidence.json produced",
        }
        _write_report(report)
        print("livekit-media-gate: no evidence artifact", file=sys.stderr)
        return 1

    evidence = read_evidence(evidence_path)
    if evidence is None:
        return 1

    failure = classify_media_gate(evidence)
    evidence.failure = str(failure)
    write_evidence(evidence_path, evidence)

    raw_wav = Path(evidence.raw_inbound_wav)
    wav_ok = raw_wav.exists() and raw_wav.stat().st_size > 44

    report = {
        "status": "pass" if failure == MediaGateFailure.PASSED and wav_ok else "fail",
        "failure": str(failure),
        "failure_boundary": _failure_boundary(failure),
        "evidence_path": str(evidence_path),
        "counters": {
            "sip_rtp_rx_packets": evidence.sip_rtp_rx_packets,
            "sip_rtp_rx_bytes": evidence.sip_rtp_rx_bytes,
            "livekit_track_frames": evidence.livekit_track_frames,
            "livekit_track_bytes": evidence.livekit_track_bytes,
            "actor_pcm_frames": evidence.actor_pcm_frames,
            "actor_pcm_bytes": evidence.actor_pcm_bytes,
            "nonzero_pcm_frames": evidence.nonzero_pcm_frames,
        },
        "timestamps": {
            "invite_sent_at": evidence.invite_sent_at,
            "sip_answered_at": evidence.sip_answered_at,
            "first_livekit_frame_at": evidence.first_livekit_frame_at,
            "first_imvera_pcm_at": evidence.first_imvera_pcm_at,
        },
        "raw_inbound_wav": str(raw_wav) if wav_ok else "",
    }
    _write_report(report)

    if failure != MediaGateFailure.PASSED or not wav_ok:
        print(
            f"livekit-media-gate: FAILED boundary={report['failure_boundary']}",
            file=sys.stderr,
        )
        print(json.dumps(report, indent=2))
        return 1

    MEDIA_GATE_STAMP.parent.mkdir(parents=True, exist_ok=True)
    MEDIA_GATE_STAMP.write_text(
        json.dumps(
            {
                "passed_at": time.time(),
                "evidence_path": str(evidence_path),
                "nonzero_pcm_frames": evidence.nonzero_pcm_frames,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("livekit-media-gate: PASSED (transport P0)")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
