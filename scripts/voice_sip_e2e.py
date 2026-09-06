#!/usr/bin/env python3
"""SIP end-to-end test — real speech, trace, and bidirectional audio artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = ROOT / ".run" / "sip-e2e"
SPEECH_TEXT = "да это я"


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _generate_ulaw_speech(text: str, out_path: Path) -> None:
    aiff = out_path.with_suffix(".aiff")
    subprocess.run(["say", "-v", "Milena", text, "-o", str(aiff)], check=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(aiff),
            "-ar",
            "8000",
            "-ac",
            "1",
            "-f",
            "mulaw",
            str(out_path),
        ],
        check=True,
        capture_output=True,
    )


def _trace_events(call_id: str) -> list[dict]:
    path = ROOT / ".run" / "traces" / f"{call_id}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _wait_trace(call_id: str, required: set[str], timeout_s: float) -> set[str]:
    deadline = time.time() + timeout_s
    seen: set[str] = set()
    while time.time() < deadline:
        for row in _trace_events(call_id):
            seen.add(row["type"])
        if required <= seen:
            return seen
        time.sleep(0.5)
    return seen


def _latest_sip_call_id() -> str | None:
    traces = sorted(
        ROOT.glob(".run/traces/sip-*.jsonl"),
        key=lambda p: p.stat().st_mtime,
    )
    if not traces:
        return None
    return traces[-1].stem


def _run_sip_call(caller_ulaw: bytes) -> tuple[str | None, bytearray]:
    try:
        import audioop  # noqa: F401
    except ImportError:
        print("BLOCKED: pip install audioop-lts pyVoIP", file=sys.stderr)
        return None, bytearray()

    from pyVoIP.VoIP import VoIPPhone, CallState

    cfg = json.loads((ROOT / "config/local/zoiper.json").read_text())
    received = bytearray()
    silence = bytes([0xFF] * 160 * 50)
    phone = VoIPPhone(
        cfg["sip_server"],
        cfg["port"],
        cfg["username"],
        cfg["password"],
        sipPort=5075,
        rtpPortLow=13000,
        rtpPortHigh=13100,
    )
    phone.start()
    time.sleep(2)
    call = phone.call(cfg["vera_extension"])
    try:
        for _ in range(30):
            if call.state == CallState.ANSWERED:
                break
            time.sleep(0.5)
        else:
            print("BLOCKED: SIP call not answered", file=sys.stderr)
            return None, received

        greeting_deadline = time.time() + 25
        while time.time() < greeting_deadline:
            if len(call.RTPClients) == 1:
                chunk = call.read_audio(160, blocking=False)
                if chunk:
                    received.extend(chunk)
            call_id = _latest_sip_call_id()
            if call_id and "playback.completed" in _wait_trace(call_id, set(), 0.1):
                break
            time.sleep(0.05)

        for chunk in (caller_ulaw, silence):
            for offset in range(0, len(chunk), 160):
                call.write_audio(chunk[offset : offset + 160])
                time.sleep(0.02)

        response_deadline = time.time() + 45
        while time.time() < response_deadline:
            if len(call.RTPClients) == 1:
                chunk = call.read_audio(160, blocking=False)
                if chunk:
                    received.extend(chunk)
            time.sleep(0.05)
    finally:
        try:
            call.hangup()
        except Exception:
            pass
        phone.stop()

    return _latest_sip_call_id(), received


def main() -> int:
    print(f"git_sha: {_git_sha()}")
    code = subprocess.call([sys.executable, str(ROOT / "scripts" / "voice_doctor.py")])
    if code != 0:
        return code

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    caller_path = ARTIFACT_DIR / "caller_speech.ul"
    _generate_ulaw_speech(SPEECH_TEXT, caller_path)
    caller_ulaw = caller_path.read_bytes()

    call_id, received = _run_sip_call(caller_ulaw)
    if not call_id:
        return 1

    capture_bytes = 0
    log_path = ROOT / ".run" / "voice_gateway.log"
    if log_path.exists():
        for line in reversed(log_path.read_text(encoding="utf-8").splitlines()):
            if f"call {call_id} capture_bytes=" in line:
                capture_bytes = int(line.rsplit("=", 1)[-1].strip())
                break

    seen = {row["type"] for row in _trace_events(call_id)}
    required = {
        "call.started",
        "media.ready",
        "playback.completed",
    }
    missing = sorted(required - seen)
    if missing:
        print(f"BLOCKED: missing trace events {missing}; got {sorted(seen)}", file=sys.stderr)
        return 1

    if len(received) < 8000:
        print(
            f"BLOCKED: insufficient downlink audio ({len(received)} bytes); "
            "expected TTS greeting on SIP leg",
            file=sys.stderr,
        )
        return 1

    received_path = ARTIFACT_DIR / f"{call_id}_received.ul"
    received_path.write_bytes(bytes(received))
    wav_path = ARTIFACT_DIR / f"{call_id}_received.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "mulaw",
            "-ar",
            "8000",
            "-ac",
            "1",
            "-i",
            str(received_path),
            str(wav_path),
        ],
        check=True,
        capture_output=True,
    )

    trace_dst = ARTIFACT_DIR / f"{call_id}.jsonl"
    trace_src = ROOT / ".run" / "traces" / f"{call_id}.jsonl"
    trace_dst.write_text(trace_src.read_text(encoding="utf-8"), encoding="utf-8")

    stt_ok = "stt.final" in seen
    print(f"voice-sip-e2e: SIP call OK call_id={call_id}")
    print(f"  trace: {trace_dst}")
    print(f"  downlink audio: {wav_path} ({len(received)} bytes ulaw)")
    print(f"  capture_bytes (gateway): {capture_bytes}")
    print(f"  stt.final: {'yes' if stt_ok else 'no (use Zoiper mic for uplink proof)'}")
    if not stt_ok:
        print(
            "NOTE: automated PyVoIP uplink may not reach snoop capture; "
            "live Zoiper test is required for STT proof on SIP.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
