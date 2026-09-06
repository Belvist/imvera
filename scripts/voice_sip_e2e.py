#!/usr/bin/env python3
"""SIP voice E2E — downlink smoke and full conversation acceptance gate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = ROOT / ".run" / "sip-e2e"
GATEWAY = "http://127.0.0.1:9200"
SPEECH_TEXT = "да это я"
FRAME_BYTES = 160  # 20 ms @ 8 kHz unsigned PCM mono
SILENCE_BYTE = 0x80
PYVOIP_VERSION = "1.6.8"


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


def _require_pyvoip() -> None:
    try:
        import audioop_lts  # noqa: F401
    except ImportError:
        try:
            import audioop  # noqa: F401
        except ImportError:
            print(
                "BLOCKED: install sip-lab deps: pip install -e '.[sip-lab]'",
                file=sys.stderr,
            )
            raise SystemExit(1) from None
    try:
        import pyVoIP  # noqa: F401
    except ImportError:
        print(
            f"BLOCKED: pyVoIP=={PYVOIP_VERSION} required: pip install -e '.[sip-lab]'",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _generate_u8_speech(text: str, out_path: Path) -> None:
    wav = out_path.with_suffix(".wav")
    aiff = out_path.with_suffix(".aiff")
    subprocess.run(["say", "-v", "Milena", text, "-o", str(aiff)], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(aiff), "-ar", "8000", "-ac", "1", str(wav)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(wav),
            "-ar",
            "8000",
            "-ac",
            "1",
            "-f",
            "u8",
            str(out_path),
        ],
        check=True,
        capture_output=True,
    )


def _trace_rows(call_id: str) -> list[dict]:
    path = ROOT / ".run" / "traces" / f"{call_id}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _cleanup_stale_calls() -> None:
    try:
        r = httpx.get(f"{GATEWAY}/internal/calls/active", timeout=2.0)
        if r.status_code != 200:
            return
        for call_id in r.json().get("calls", []):
            httpx.post(f"http://127.0.0.1:9201/internal/calls/{call_id}/hangup", timeout=5.0)
            httpx.post(f"{GATEWAY}/internal/calls/{call_id}/close", timeout=5.0)
    except httpx.HTTPError:
        pass


def _wait_new_call(since_ts: float, timeout_s: float = 20.0) -> str | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        candidates = []
        for path in ROOT.glob(".run/traces/sip-*.jsonl"):
            if path.stat().st_mtime >= since_ts - 0.5:
                candidates.append((path.stat().st_mtime, path.stem))
        if candidates:
            candidates.sort(key=lambda item: item[0])
            return candidates[-1][1]
        time.sleep(0.1)
    return None


def _wait_trace_types(call_id: str, required: set[str], timeout_s: float) -> set[str]:
    deadline = time.time() + timeout_s
    seen: set[str] = set()
    while time.time() < deadline:
        for row in _trace_rows(call_id):
            seen.add(row["type"])
        if required <= seen:
            return seen
        time.sleep(0.2)
    for row in _trace_rows(call_id):
        seen.add(row["type"])
    return seen


def _call_capture_bytes(call_id: str) -> int:
    try:
        r = httpx.get(f"{GATEWAY}/internal/calls/{call_id}/status", timeout=2.0)
        if r.status_code == 200:
            return int(r.json().get("capture_bytes", 0))
    except httpx.HTTPError:
        pass
    return 0


def _save_pcm_wav(pcm_u8: bytes, wav_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "u8",
            "-ar",
            "8000",
            "-ac",
            "1",
            "-i",
            "pipe:0",
            str(wav_path),
        ],
        input=pcm_u8,
        check=True,
        capture_output=True,
    )


def _collect_downlink(call, seconds: float = 4.0) -> bytes:
    """Blocking read after greeting — avoids PyVoIP non-blocking silence-only polling."""
    buf = bytearray()
    deadline = time.time() + seconds
    while time.time() < deadline and len(buf) < _AudioTap._MAX_BYTES:
        try:
            chunk = call.read_audio(FRAME_BYTES, blocking=True)
        except (IndexError, Exception):
            time.sleep(0.01)
            continue
        if chunk:
            buf.extend(chunk)
    return bytes(buf)


class _AudioTap:
    """Collect downlink PCM from PyVoIP; cap buffer to avoid silence padding blow-up."""

    _MAX_BYTES = 8000 * 30  # 30 s @ 8 kHz mono u8

    def __init__(self) -> None:
        self._buf = bytearray()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, call) -> None:
        def _loop() -> None:
            while not self._stop.is_set() and len(self._buf) < self._MAX_BYTES:
                clients = getattr(call, "RTPClients", None)
                if not clients or len(clients) != 1:
                    time.sleep(0.01)
                    continue
                try:
                    chunk = call.read_audio(FRAME_BYTES, blocking=True)
                except (IndexError, Exception):
                    time.sleep(0.01)
                    continue
                if chunk:
                    self._buf.extend(chunk)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> bytes:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        return bytes(self._buf)


def _run_sip_session(
    caller_pcm: bytes, *, send_speech: bool
) -> tuple[str | None, bytes, str | None, int]:
    from pyVoIP.VoIP import CallState, VoIPPhone

    cfg = json.loads((ROOT / "config/local/zoiper.json").read_text())
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
    since_ts = time.time()
    call = phone.call(cfg["vera_extension"])
    sip_call_id = getattr(call, "call_id", None)
    internal_call_id: str | None = None
    tap = _AudioTap()
    received = b""
    capture_bytes = 0
    try:
        for _ in range(40):
            if call.state == CallState.ANSWERED:
                break
            time.sleep(0.25)
        else:
            print("BLOCKED: SIP call not answered", file=sys.stderr)
            return None, b"", sip_call_id, 0

        internal_call_id = _wait_new_call(since_ts, 20.0)
        if not internal_call_id:
            print("BLOCKED: no new gateway call_id after SIP answer", file=sys.stderr)
            return None, b"", sip_call_id, 0

        tap.start(call)
        _wait_trace_types(internal_call_id, {"playback.completed"}, 30.0)

        if send_speech:
            silence = bytes([SILENCE_BYTE]) * FRAME_BYTES * 50
            for chunk in (caller_pcm, silence):
                for offset in range(0, len(chunk), FRAME_BYTES):
                    call.write_audio(chunk[offset : offset + FRAME_BYTES])
                    time.sleep(0.02)
            _wait_trace_types(
                internal_call_id,
                {"stt.final", "interpretation.ready", "playback.completed"},
                60.0,
            )
            time.sleep(2.0)

        capture_bytes = _call_capture_bytes(internal_call_id) if internal_call_id else 0
    finally:
        received = tap.stop() if tap._thread else _collect_downlink(call, seconds=0.5)
        try:
            call.hangup()
        except Exception:
            pass
        phone.stop()
        if send_speech and internal_call_id:
            _wait_trace_types(internal_call_id, {"call.ended"}, 10.0)

    return internal_call_id, received, sip_call_id, capture_bytes


def _assert_downlink(received: bytes, call_id: str) -> None:
    non_silence = sum(1 for b in received if b != SILENCE_BYTE)
    if non_silence < FRAME_BYTES * 5:
        raise AssertionError(
            f"insufficient downlink voice energy ({non_silence} non-silence bytes); "
            f"expected audible greeting"
        )
    seen = {row["type"] for row in _trace_rows(call_id)}
    missing = {"call.started", "media.ready", "playback.completed"} - seen
    if missing:
        raise AssertionError(f"missing downlink trace events {sorted(missing)}")


def _assert_full_conversation(received: bytes, call_id: str, capture_bytes: int) -> None:
    rows = _trace_rows(call_id)
    seen = {row["type"] for row in rows}
    required = {
        "call.started",
        "media.ready",
        "stt.final",
        "interpretation.ready",
        "playback.completed",
        "call.ended",
    }
    missing = required - seen
    if missing:
        raise AssertionError(f"missing trace events {sorted(missing)}; got {sorted(seen)}")

    if capture_bytes <= 0:
        raise AssertionError(f"capture_bytes={capture_bytes}; uplink audio not received")

    stt_texts = [
        str(row.get("payload", {}).get("text", "")).lower()
        for row in rows
        if row.get("type") == "stt.final"
    ]
    if not stt_texts or not any("да" in t for t in stt_texts):
        raise AssertionError(f"STT did not match test phrase; got {stt_texts}")

    phrases = [
        row.get("payload", {}).get("text", "")
        for row in rows
        if row.get("type") == "renderer.phrase_ready"
    ]
    if len(phrases) < 2:
        raise AssertionError("expected greeting + follow-up renderer phrases")
    if phrases[0] == phrases[1]:
        raise AssertionError("dialogue did not advance after user reply")

    completed = [
        row
        for row in rows
        if row.get("type") == "playback.completed"
        and int(row.get("payload", {}).get("sent_samples", 0)) > 0
    ]
    if len(completed) < 2:
        raise AssertionError("expected at least two non-empty playback.completed events")

    if len(received) < FRAME_BYTES * 20:
        raise AssertionError(f"insufficient downlink PCM for response ({len(received)} bytes)")

    ended = [row for row in rows if row.get("type") == "call.ended"]
    if len(ended) != 1:
        raise AssertionError(f"expected exactly one call.ended, got {len(ended)}")


def _write_artifacts(
    call_id: str, received: bytes, sip_call_id: str | None, capture_bytes: int
) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    pcm_path = ARTIFACT_DIR / f"{call_id}_received.pcm"
    wav_path = ARTIFACT_DIR / f"{call_id}_received.wav"
    pcm_path.write_bytes(received)
    _save_pcm_wav(received, wav_path)
    trace_dst = ARTIFACT_DIR / f"{call_id}.jsonl"
    trace_src = ROOT / ".run" / "traces" / f"{call_id}.jsonl"
    trace_dst.write_text(trace_src.read_text(encoding="utf-8"), encoding="utf-8")
    meta = {
        "internal_call_id": call_id,
        "sip_call_id": sip_call_id,
        "capture_bytes": capture_bytes,
        "received_pcm_bytes": len(received),
    }
    (ARTIFACT_DIR / f"{call_id}_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return wav_path


def run_downlink_smoke() -> int:
    print(f"git_sha: {_git_sha()}")
    code = subprocess.call([sys.executable, str(ROOT / "scripts" / "voice_doctor.py")])
    if code != 0:
        return code
    _require_pyvoip()
    _cleanup_stale_calls()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    caller_path = ARTIFACT_DIR / "caller_speech.pcm"
    _generate_u8_speech(SPEECH_TEXT, caller_path)
    call_id, received, sip_call_id, capture_bytes = _run_sip_session(
        caller_path.read_bytes(), send_speech=False
    )
    if not call_id:
        return 1
    try:
        _assert_downlink(received, call_id)
    except AssertionError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    wav_path = _write_artifacts(call_id, received, sip_call_id, capture_bytes)
    print(f"voice-sip-downlink-smoke OK call_id={call_id}")
    print(f"  trace: {ARTIFACT_DIR / f'{call_id}.jsonl'}")
    print(f"  audio: {wav_path}")
    return 0


def run_full_conversation() -> int:
    print(f"git_sha: {_git_sha()}")
    code = subprocess.call([sys.executable, str(ROOT / "scripts" / "voice_doctor.py")])
    if code != 0:
        return code
    _require_pyvoip()
    _cleanup_stale_calls()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    caller_path = ARTIFACT_DIR / "caller_speech.pcm"
    _generate_u8_speech(SPEECH_TEXT, caller_path)
    call_id, received, sip_call_id, capture_bytes = _run_sip_session(
        caller_path.read_bytes(), send_speech=True
    )
    if not call_id:
        return 1
    try:
        _assert_full_conversation(received, call_id, capture_bytes)
    except AssertionError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    wav_path = _write_artifacts(call_id, received, sip_call_id, capture_bytes)
    print(f"voice-sip-e2e: full conversation OK call_id={call_id}")
    print(f"  trace: {ARTIFACT_DIR / f'{call_id}.jsonl'}")
    print(f"  audio: {wav_path}")
    print(f"  capture_bytes: {capture_bytes}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SIP voice E2E acceptance")
    parser.add_argument(
        "--downlink-only",
        action="store_true",
        help="Run greeting/downlink smoke only (no uplink STT gate)",
    )
    args = parser.parse_args()
    if args.downlink_only:
        return run_downlink_smoke()
    return run_full_conversation()


if __name__ == "__main__":
    raise SystemExit(main())
