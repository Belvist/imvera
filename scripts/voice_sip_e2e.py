#!/usr/bin/env python3
"""SIP voice E2E — downlink smoke and full conversation acceptance gate."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = ROOT / ".run" / "sip-e2e"
RESULT_PATH = ARTIFACT_DIR / "result.json"
GATEWAY = os.environ.get("IMVERA_VOICE_GATEWAY_HTTP", "http://127.0.0.1:9200")
SPEECH_TEXT = "да это я"
FRAME_BYTES = 160  # 20 ms @ 8 kHz unsigned PCM mono
SILENCE_BYTE = 0x80
PYVOIP_VERSION = "1.6.8"
DEFAULT_SIP_PORT = int(os.environ.get("IMVERA_E2E_SIP_PORT", "5075"))
DEFAULT_SUBPROCESS_TIMEOUT_S = int(os.environ.get("IMVERA_E2E_TIMEOUT_S", "180"))
MIN_USER_TURNS = int(os.environ.get("IMVERA_E2E_MIN_USER_TURNS", "2"))


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


def _write_result(status: str, **payload: object) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    body = {
        "status": status,
        "git_sha": _git_sha(),
        "updated_at": time.time(),
        **payload,
    }
    RESULT_PATH.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")


def _preflight_sip_port(port: int) -> None:
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", port))
    except OSError as exc:
        raise RuntimeError(
            f"SIP test port {port} is already in use; set IMVERA_E2E_SIP_PORT"
        ) from exc
    finally:
        probe.close()


def _cleanup_call(call_id: str | None) -> None:
    if not call_id:
        return
    try:
        httpx.post(f"http://127.0.0.1:9201/internal/calls/{call_id}/hangup", timeout=5.0)
        httpx.post(f"{GATEWAY}/internal/calls/{call_id}/close", timeout=5.0)
    except httpx.HTTPError:
        pass


def _cleanup_stale_calls() -> None:
    """Legacy helper — avoid closing unrelated active calls in normal runner."""
    return


def _wait_new_call(since_ts: float, timeout_s: float = 20.0, sip_call_id: str | None = None) -> str | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        candidates = []
        for path in ROOT.glob(".run/traces/sip-*.jsonl"):
            if path.stat().st_mtime >= since_ts - 0.5:
                candidates.append((path.stat().st_mtime, path.stem))
        if candidates:
            candidates.sort(key=lambda item: item[0])
            chosen = candidates[-1][1]
            if sip_call_id:
                rows = _trace_rows(chosen)
                linked = any(
                    row.get("payload", {}).get("sip_call_id") == sip_call_id
                    for row in rows
                )
                if not linked and len(candidates) > 1:
                    time.sleep(0.1)
                    continue
            return chosen
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


def _prime_rtp_symmetric(call) -> None:
    """Send uplink silence so Asterisk learns client RTP source (Docker NAT)."""
    silence = bytes([SILENCE_BYTE]) * FRAME_BYTES
    for _ in range(30):
        try:
            call.write_audio(silence)
        except Exception:
            break
        time.sleep(0.02)


def _run_sip_session(
    caller_pcm: bytes, *, send_speech: bool, sip_port: int = DEFAULT_SIP_PORT
) -> tuple[str | None, bytes, str | None, int]:
    from pyVoIP.VoIP import CallState, VoIPPhone

    cfg = json.loads((ROOT / "config/local/zoiper.json").read_text())
    e2e = cfg.get("e2e_account") or {}
    sip_user = e2e.get("username") or cfg["username"]
    sip_pass = e2e.get("password") or cfg["password"]
    media_host = cfg.get("media_host") or cfg["sip_server"]
    sip_server = cfg.get("sip_server") or media_host
    phone = VoIPPhone(
        sip_server,
        cfg["port"],
        sip_user,
        sip_pass,
        myIP=media_host,
        sipPort=sip_port,
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

        internal_call_id = _wait_new_call(since_ts, 20.0, sip_call_id=sip_call_id)
        if not internal_call_id:
            print("BLOCKED: no new gateway call_id after SIP answer", file=sys.stderr)
            return None, b"", sip_call_id, 0

        _prime_rtp_symmetric(call)
        tap.start(call)
        _wait_trace_types(internal_call_id, {"playback.completed"}, 45.0)

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


def _downlink_energy(received: bytes) -> int:
    return sum(1 for b in received if b != SILENCE_BYTE)


def _assert_full_conversation(received: bytes, call_id: str, capture_bytes: int) -> None:
    non_silence = _downlink_energy(received)
    if non_silence < FRAME_BYTES * 5:
        raise AssertionError(
            f"insufficient downlink voice energy ({non_silence} non-silence bytes); "
            f"silence-only capture is not a conversation"
        )

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

    stt_rows = [row for row in rows if row.get("type") == "stt.final"]
    stt_texts = [str(row.get("payload", {}).get("text", "")).lower() for row in stt_rows]
    if len(stt_texts) < MIN_USER_TURNS:
        raise AssertionError(
            f"expected at least {MIN_USER_TURNS} user turns, got {len(stt_texts)}"
        )
    if not any("да" in t for t in stt_texts):
        raise AssertionError(f"STT did not match test phrase; got {stt_texts}")

    phrases = [
        row.get("payload", {}).get("text", "")
        for row in rows
        if row.get("type") == "renderer.phrase_ready"
    ]
    if len(phrases) < MIN_USER_TURNS + 1:
        raise AssertionError(
            f"expected greeting plus {MIN_USER_TURNS} follow-up renderer phrases"
        )
    if len(set(phrases)) < MIN_USER_TURNS + 1:
        raise AssertionError("dialogue did not advance across turns")

    completed = [
        row
        for row in rows
        if row.get("type") == "playback.completed"
        and int(row.get("payload", {}).get("sent_samples", 0)) > 0
    ]
    if len(completed) < MIN_USER_TURNS + 1:
        raise AssertionError(
            f"expected at least {MIN_USER_TURNS + 1} non-empty playback.completed events"
        )

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


def run_downlink_smoke(sip_port: int = DEFAULT_SIP_PORT) -> int:
    print(f"git_sha: {_git_sha()}", flush=True)
    _write_result("RUNNING", mode="downlink-only", stage="preflight")
    code = subprocess.call([sys.executable, str(ROOT / "scripts" / "voice_doctor.py")])
    if code != 0:
        _write_result("FAILED", mode="downlink-only", stage="voice_doctor", exit_code=code)
        return code
    _require_pyvoip()
    _preflight_sip_port(sip_port)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    caller_path = ARTIFACT_DIR / "caller_speech.pcm"
    _generate_u8_speech(SPEECH_TEXT, caller_path)
    call_id: str | None = None
    try:
        call_id, received, sip_call_id, capture_bytes = _run_sip_session(
            caller_path.read_bytes(), send_speech=False, sip_port=sip_port
        )
        if not call_id:
            _write_result("FAILED", mode="downlink-only", stage="sip_session")
            return 1
        _assert_downlink(received, call_id)
    except AssertionError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr, flush=True)
        _write_result(
            "FAILED",
            mode="downlink-only",
            call_id=call_id,
            error=str(exc),
        )
        return 1
    finally:
        _cleanup_call(call_id)
    wav_path = _write_artifacts(call_id, received, sip_call_id, capture_bytes)
    _write_result(
        "PASSED",
        mode="downlink-only",
        call_id=call_id,
        wav_path=str(wav_path),
    )
    print(f"voice-sip-downlink-smoke OK call_id={call_id}", flush=True)
    print(f"  trace: {ARTIFACT_DIR / f'{call_id}.jsonl'}", flush=True)
    print(f"  audio: {wav_path}", flush=True)
    return 0


def run_full_conversation(sip_port: int = DEFAULT_SIP_PORT) -> int:
    print(f"git_sha: {_git_sha()}", flush=True)
    _write_result("RUNNING", mode="full-conversation", stage="preflight")
    code = subprocess.call([sys.executable, str(ROOT / "scripts" / "voice_doctor.py")])
    if code != 0:
        _write_result("FAILED", mode="full-conversation", stage="voice_doctor", exit_code=code)
        return code
    _require_pyvoip()
    _preflight_sip_port(sip_port)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    caller_path = ARTIFACT_DIR / "caller_speech.pcm"
    _generate_u8_speech(SPEECH_TEXT, caller_path)
    call_id: str | None = None
    try:
        call_id, received, sip_call_id, capture_bytes = _run_sip_session(
            caller_path.read_bytes(), send_speech=True, sip_port=sip_port
        )
        if not call_id:
            _write_result("FAILED", mode="full-conversation", stage="sip_session")
            return 1
        _assert_full_conversation(received, call_id, capture_bytes)
    except AssertionError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr, flush=True)
        _write_result(
            "FAILED",
            mode="full-conversation",
            call_id=call_id,
            error=str(exc),
        )
        return 1
    finally:
        _cleanup_call(call_id)
    wav_path = _write_artifacts(call_id, received, sip_call_id, capture_bytes)
    _write_result(
        "PASSED",
        mode="full-conversation",
        call_id=call_id,
        capture_bytes=capture_bytes,
        wav_path=str(wav_path),
    )
    print(f"voice-sip-e2e: full conversation OK call_id={call_id}", flush=True)
    print(f"  trace: {ARTIFACT_DIR / f'{call_id}.jsonl'}", flush=True)
    print(f"  audio: {wav_path}", flush=True)
    print(f"  capture_bytes: {capture_bytes}", flush=True)
    return 0


def _child_entry(mode: str, sip_port: int) -> int:
    if mode == "downlink-only":
        return run_downlink_smoke(sip_port=sip_port)
    return run_full_conversation(sip_port=sip_port)


def _run_with_subprocess_deadline(
    mode: str,
    *,
    sip_port: int,
    timeout_s: int,
) -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_result("RUNNING", mode=mode, stage="spawn", timeout_s=timeout_s)
    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "scripts" / "voice_sip_e2e.py"),
        "--child",
        mode,
        "--sip-port",
        str(sip_port),
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        stdout, _ = proc.communicate(timeout=timeout_s)
        if stdout:
            print(stdout, end="", flush=True)
        if proc.returncode is None:
            proc.wait(timeout=1)
        if RESULT_PATH.exists():
            result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
            if result.get("status") == "RUNNING":
                _write_result(
                    "FAILED",
                    mode=mode,
                    error="child exited without final result status",
                    exit_code=proc.returncode,
                )
        return int(proc.returncode or 0)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        stdout, _ = proc.communicate(timeout=5)
        if stdout:
            print(stdout, end="", flush=True)
        _write_result(
            "TIMED_OUT",
            mode=mode,
            timeout_s=timeout_s,
            output_tail=(stdout or "").splitlines()[-20:],
        )
        print(f"BLOCKED: timed out after {timeout_s}s", file=sys.stderr, flush=True)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="SIP voice E2E acceptance")
    parser.add_argument(
        "--downlink-only",
        action="store_true",
        help="Run greeting/downlink smoke only (no uplink STT gate)",
    )
    parser.add_argument(
        "--child",
        choices=("downlink-only", "full-conversation"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--sip-port",
        type=int,
        default=DEFAULT_SIP_PORT,
        help=f"SIP client bind port (default {DEFAULT_SIP_PORT})",
    )
    parser.add_argument(
        "--timeout-s",
        type=int,
        default=DEFAULT_SUBPROCESS_TIMEOUT_S,
        help=f"Parent wall-clock deadline in seconds (default {DEFAULT_SUBPROCESS_TIMEOUT_S})",
    )
    args = parser.parse_args()
    mode = "downlink-only" if args.downlink_only else "full-conversation"
    if args.child:
        return _child_entry(args.child, sip_port=args.sip_port)
    return _run_with_subprocess_deadline(
        mode,
        sip_port=args.sip_port,
        timeout_s=args.timeout_s,
    )


if __name__ == "__main__":
    raise SystemExit(main())
