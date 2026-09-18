#!/usr/bin/env python3
"""One-call SIP diagnostic archive — runtime truth, trace, logs, WS diag, WAV."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.local_sip_config import load_or_create

RUN = ROOT / ".run"
DIAG_ROOT = RUN / "diag"
REDACT_PATTERNS = (
    (
        re.compile(r"(password|token|secret|authorization)\s*[:=]\s*['\"]?\S+", re.I),
        r"\1=***REDACTED***",
    ),
    (re.compile(r"postgresql://[^:]+:[^@]+@"), "postgresql://imvera:***REDACTED***@"),
)


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _docker(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
    except subprocess.CalledProcessError as exc:
        return exc.output.strip() if exc.output else str(exc)


def _redact(text: str) -> str:
    for pattern, repl in REDACT_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def _runtime_manifest() -> dict:
    sha = _git_sha()
    asterisk_version = _docker(
        ["docker", "exec", "imvera-asterisk", "asterisk", "-rx", "core show version"]
    )
    ws_modules = _docker(
        ["docker", "exec", "imvera-asterisk", "asterisk", "-rx", "module show like websocket"]
    )
    image_id = _docker(["docker", "inspect", "imvera-asterisk", "--format", "{{.Image}}"])
    container_id = _docker(["docker", "inspect", "imvera-asterisk", "--format", "{{.Id}}"])[:12]

    pids: dict[str, str] = {}
    for name in ("voice_gateway", "asterisk_app", "stt", "tts", "llm"):
        pid_path = RUN / f"{name}.pid"
        if pid_path.exists():
            pids[name] = pid_path.read_text().strip()

    stt = os.environ.get("IMVERA_STT_URL", "http://127.0.0.1:9101")
    tts = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    llm = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103")

    chan_ws = ""
    chan_path = ROOT / "config/local/asterisk/chan_websocket.conf"
    if chan_path.exists():
        chan_ws = chan_path.read_text(encoding="utf-8")

    return {
        "collected_at": datetime.now(UTC).isoformat(),
        "git_sha": sha,
        "process_pids": pids,
        "endpoints": {"stt": stt, "tts": tts, "llm": llm, "gateway": "http://127.0.0.1:9200"},
        "asterisk": {
            "container_id": container_id,
            "image_id": image_id,
            "version": asterisk_version,
            "websocket_modules": ws_modules,
            "chan_websocket_conf": chan_ws,
        },
    }


def _fetch_greeting_wav(out_path: Path) -> dict:
    """Synthesize greeting text via TTS for offline listening."""
    import base64

    tts_url = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    elder = os.environ.get("IMVERA_ELDER_DISPLAY_NAME", "Даниил")
    text = f"Здравствуйте. Я Вера, голосовой помощник IMVERA. Я разговариваю с {elder}?"
    meta: dict = {"text": text, "tts_url": tts_url}
    try:
        with httpx.stream(
            "POST",
            f"{tts_url}/v1/synthesize",
            json={"text": text, "sample_rate": 16000, "generation_id": "diag-greeting"},
            timeout=120.0,
        ) as r:
            meta["http_status"] = r.status_code
            if r.status_code != 200:
                meta["error"] = r.read().decode()[:500]
                return meta
            pcm = bytearray()
            sample_rate = 16000
            for line in r.iter_lines():
                if not line:
                    continue
                row = json.loads(line)
                if row.get("done"):
                    break
                if "pcm_b64" in row:
                    pcm.extend(base64.b64decode(row["pcm_b64"]))
                    sample_rate = int(row.get("sample_rate", sample_rate))
            meta["pcm_bytes"] = len(pcm)
            if pcm:
                raw = out_path.with_suffix(".raw_pcm")
                raw.write_bytes(bytes(pcm))
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "s16le",
                        "-ar",
                        str(sample_rate),
                        "-ac",
                        "1",
                        "-i",
                        str(raw),
                        str(out_path),
                    ],
                    check=False,
                    capture_output=True,
                )
                meta["wav_path"] = str(out_path.name)
    except Exception as exc:
        meta["exception"] = repr(exc)
    return meta


def _diagnose_call(call_id: str, manifest: dict) -> dict:
    trace_path = RUN / "traces" / f"{call_id}.jsonl"
    ws_path = RUN / "ws-diag" / f"{call_id}.jsonl"
    rows = []
    if trace_path.exists():
        rows = [json.loads(line) for line in trace_path.read_text().splitlines() if line]
    types = {r.get("type") for r in rows}
    ws_rows = []
    if ws_path.exists():
        ws_rows = [json.loads(line) for line in ws_path.read_text().splitlines() if line]

    playback = next((r for r in rows if r.get("type") == "playback.completed"), None)
    sent = int((playback or {}).get("payload", {}).get("sent_samples", 0))

    findings = []
    if ws_rows:
        findings.append(
            "MEDIA_START: JSON control messages received on capture+inject (not plain-text drop)."
        )
    else:
        findings.append("MEDIA_START: no ws-diag capture (set IMVERA_WS_DIAG=1).")

    if "media.ready" in types:
        findings.append("Greeting gate: media.ready fired → on_media_ready reached.")
    else:
        findings.append("Greeting gate: media.ready MISSING — check WS attach order.")

    if sent > 0:
        findings.append(
            f"TTS/inject: playback.completed sent_samples={sent} (gateway sent PCM to inject WS)."
        )
    else:
        findings.append("TTS/inject: no samples sent to inject.")

    findings.append(
        "RTP to phone: NOT VERIFIED — PyVoIP downlink 0 non-silence bytes; "
        "Asterisk native beep also fails in container. "
        f"Configured media_host={manifest.get('media_host', 'unknown')} "
        "(client SDP + pjsip external_media_address must match a host-routable IP)."
    )

    return {
        "call_id": call_id,
        "trace_event_types": sorted(types),
        "ws_control_messages": len(ws_rows),
        "sent_samples": sent,
        "first_break_hypothesis": "Asterisk→client RTP (Docker NAT), not MEDIA_START parsing",
        "findings": findings,
    }


def _run_downlink_call() -> tuple[str | None, int]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "voice_sip_e2e.py"), "--downlink-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    call_id = None
    for line in proc.stdout.splitlines():
        if "call_id=" in line:
            call_id = line.split("call_id=")[-1].strip()
    return call_id, proc.returncode


def _latest_trace_call_id(since: float) -> str | None:
    candidates = []
    for path in (RUN / "traces").glob("sip-*.jsonl"):
        if path.stat().st_mtime >= since - 1.0:
            candidates.append((path.stat().st_mtime, path.stem))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]


def _copy_logs(call_id: str, dest: Path) -> None:
    for name in ("voice_gateway", "asterisk_app"):
        src = RUN / f"{name}.log"
        if src.exists():
            shutil.copy2(src, dest / f"{name}.log")

    try:
        asterisk_log = subprocess.check_output(
            ["docker", "logs", "--tail", "500", "imvera-asterisk"],
            stderr=subprocess.STDOUT,
            text=True,
        )
        (dest / "asterisk_container.log").write_text(_redact(asterisk_log), encoding="utf-8")
    except subprocess.CalledProcessError:
        pass

    ws_diag = RUN / "ws-diag" / f"{call_id}.jsonl"
    if ws_diag.exists():
        shutil.copy2(ws_diag, dest / f"{call_id}_ws_control.jsonl")

    trace = RUN / "traces" / f"{call_id}.jsonl"
    if trace.exists():
        shutil.copy2(trace, dest / f"{call_id}.jsonl")

    sip_e2e = RUN / "sip-e2e"
    if sip_e2e.exists():
        for f in sip_e2e.glob(f"{call_id}*"):
            shutil.copy2(f, dest / f.name)


def build_archive(call_id: str | None = None, skip_call: bool = False) -> Path:
    cfg = load_or_create()
    manifest = _runtime_manifest()
    manifest["media_host"] = cfg.get("media_host")

    e2e_rc = 0
    if not skip_call:
        since = time.time()
        call_id, e2e_rc = _run_downlink_call()
        if not call_id:
            call_id = _latest_trace_call_id(since)

    if not call_id:
        call_id = f"unknown-{int(time.time())}"

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    bundle_dir = DIAG_ROOT / f"{stamp}_{call_id}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    greeting_meta = _fetch_greeting_wav(bundle_dir / "greeting_tts.wav")
    manifest["greeting_tts"] = greeting_meta
    manifest["call_id"] = call_id
    manifest["e2e_downlink_exit_code"] = e2e_rc
    manifest["diagnosis"] = _diagnose_call(call_id, manifest)

    if call_id.startswith("sip-"):
        try:
            r = httpx.get(f"http://127.0.0.1:9200/internal/calls/{call_id}/status", timeout=2.0)
            if r.status_code == 200:
                manifest["final_call_status"] = r.json()
        except httpx.HTTPError:
            pass

    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (bundle_dir / "DIAGNOSIS.md").write_text(
        "\n".join(
            ["# SIP call diagnosis", "", *[f"- {f}" for f in manifest["diagnosis"]["findings"]], ""]
        ),
        encoding="utf-8",
    )
    _copy_logs(call_id, bundle_dir)

    for path in bundle_dir.iterdir():
        if path.suffix in (".log", ".jsonl") and path.is_file():
            path.write_text(_redact(path.read_text(encoding="utf-8")), encoding="utf-8")

    zip_path = DIAG_ROOT / f"{stamp}_{call_id}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in bundle_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(bundle_dir))
    print(f"Diagnostic bundle: {zip_path}")
    print(f"  call_id: {call_id}")
    print(f"  e2e exit: {e2e_rc}")
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build one-call SIP diagnostic archive")
    parser.add_argument("--call-id", help="Use existing call_id instead of placing new call")
    parser.add_argument(
        "--skip-call", action="store_true", help="Only collect runtime + last trace"
    )
    args = parser.parse_args()
    build_archive(call_id=args.call_id, skip_call=args.skip_call or bool(args.call_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
