#!/usr/bin/env python3
"""Owner voice gate — 10 pronunciation phrases via live Silero TTS.

Checks stress, full-phrase intonation, and logs the exact text sent to Silero.

Usage:
    python3 scripts/run_pronunciation_voice_gate.py
    python3 scripts/run_pronunciation_voice_gate.py --host 127.0.0.1 --port 9600
    afplay voice_gate_runs/latest/01_imvera.wav   # listen locally

Live Zoiper gate (owner):
    1. Enable trace: MOSS_TTS_TRACE=1 on voice container, restart telephony
    2. Dial 4400, trigger each phrase in conversation
    3. docker logs mossvoice-telephony 2>&1 | grep -A3 TTS_TRACE
    4. PASS only if stress + intonation + no stitch artifacts on all 10

Exit 0 when all phrases synthesized; exit 2 if voice service unreachable.
Human PASS/FAIL is owner ears — this script prepares WAV + trace JSON.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_MOSS_RT = _REPO / "runtime" / "scripts" / "moss_runtime"
if str(_MOSS_RT) not in sys.path:
    sys.path.insert(0, str(_MOSS_RT))

from speech_frontend import build_tts_trace, format_tts_trace_lines  # noqa: E402

VOICE_GATE_PHRASES: tuple[tuple[str, str], ...] = (
    ("01_imvera", "Имвера"),
    ("02_pozvonit", "позвонит"),
    ("03_zvonit", "звонит"),
    ("04_davlenie", "давление"),
    ("05_lekarstva", "лекарства"),
    ("06_rodnye", "родные"),
    ("07_segodnya_vecherom", "сегодня вечером"),
    ("08_wellness_question", "Как вы сегодня себя чувствуете?"),
    (
        "09_correction_spine",
        "Поняла, спасибо за уточнение — речь о спине.",
    ),
    ("10_goodbye", "Хорошо. Берегите себя, до свидания."),
)

CONTEXT_PHRASES: tuple[tuple[str, str], ...] = (
    ("ctx_imvera_call", "Имвера позвонит вам сегодня вечером."),
    (
        "ctx_meds_pressure",
        "Вы принимали лекарства? Как давление сегодня?",
    ),
)


def _health(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://{host}:{port}/health",
            timeout=5,
        ) as resp:
            data = json.loads(resp.read().decode())
        return bool(data.get("ready"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False


def _synthesize(host: str, port: int, text: str) -> tuple[bytes, dict | None]:
    payload = json.dumps(
        {
            "text": text,
            "refs": [],
            "style_enabled": False,
        }
    ).encode()
    req = urllib.request.Request(
        f"http://{host}:{port}/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        obj = json.loads(resp.read().decode())
    if not obj.get("ok"):
        raise RuntimeError(obj.get("error") or "TTS failed")
    wav = base64.b64decode(obj["wav_b64"])
    return wav, obj.get("tts_trace")


def _write_wav(path: Path, pcm: bytes, sample_rate: int = 48000) -> None:
    import struct

    channels = 1
    bits = 16
    # Silero returns float in server — wav_b64 is already WAV from make_wav_bytes
    path.write_bytes(pcm)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pronunciation owner voice gate")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9600)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_REPO / "voice_gate_runs",
    )
    parser.add_argument(
        "--with-context",
        action="store_true",
        help="Also synthesize full-sentence context variants",
    )
    parser.add_argument(
        "--trace-only",
        action="store_true",
        help="Print traces without calling TTS (offline)",
    )
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = args.out_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    latest = args.out_dir / "latest"
    if latest.is_symlink() or latest.exists():
        if latest.is_symlink():
            latest.unlink()
        elif latest.is_dir():
            pass
    try:
        latest.symlink_to(run_dir.name, target_is_directory=True)
    except OSError:
        pass

    if not args.trace_only and not _health(args.host, args.port):
        print(f"VOICE_GATE_STATUS=BLOCKED voice not ready at {args.host}:{args.port}")
        return 2

    cases = list(VOICE_GATE_PHRASES)
    if args.with_context:
        cases.extend(CONTEXT_PHRASES)

    report: list[dict] = []
    print(f"VOICE_GATE_RUN={run_dir}")
    print("=" * 60)

    for case_id, text in cases:
        local_trace = build_tts_trace(text)
        entry: dict = {
            "id": case_id,
            "text": text,
            "local_trace": local_trace,
            "wav": None,
            "server_trace": None,
            "owner_verdict": "PENDING",
        }
        print(f"\n[{case_id}] {text}")
        print(format_tts_trace_lines(local_trace))
        if local_trace.get("TTS_SSML"):
            print(f'TTS_SSML: "{local_trace["TTS_SSML"]}"')

        if not args.trace_only:
            wav, server_trace = _synthesize(args.host, args.port, text)
            wav_path = run_dir / f"{case_id}.wav"
            _write_wav(wav_path, wav)
            entry["wav"] = str(wav_path)
            entry["server_trace"] = server_trace
            if server_trace:
                print("--- server trace ---")
                print(format_tts_trace_lines(server_trace))
            print(f"WAV: {wav_path} ({len(wav)} bytes) — afplay to listen")

        report.append(entry)

    summary = {
        "status": "AWAITING_OWNER_EARS",
        "run_dir": str(run_dir),
        "phrase_count": len(cases),
        "criteria": [
            "stress_correct",
            "phrase_intonation_natural",
            "no_stitch_artifacts_around_stress_marks",
        ],
        "phrases": report,
        "live_zoiper_hint": (
            "MOSS_TTS_TRACE=1 on mossvoice-voice; docker logs mossvoice-telephony | TTS_TRACE"
        ),
    }
    summary_path = run_dir / "voice_gate_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\n" + "=" * 60)
    print("VOICE_GATE_STATUS=AWAITING_OWNER_EARS")
    print(f"summary={summary_path}")
    print("Owner: listen to each WAV (or live call). Mark PASS/FAIL in summary JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
