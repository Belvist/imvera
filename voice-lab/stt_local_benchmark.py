#!/usr/bin/env python3
"""STT local benchmark scaffold — GigaAM / Nemotron / Qwen3-ASR (P1).

Usage (offline, no network):
  python3 voice-lab/stt_local_benchmark.py --list
  python3 voice-lab/stt_local_benchmark.py --model gigaam --wav path/to.wav
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SUPPORTED_MODELS = ("gigaam", "nemotron", "qwen3-asr", "whisper-local")


def _transcribe_gigaam(wav_path: Path) -> tuple[str, float]:
    """GigaAM path — host service not wired; scaffold returns empty."""
    t0 = time.perf_counter()
    elapsed = time.perf_counter() - t0
    return "", elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description="STT local benchmark scaffold")
    parser.add_argument("--list", action="store_true", help="List supported models")
    parser.add_argument("--model", choices=SUPPORTED_MODELS, default="whisper-local")
    parser.add_argument("--wav", type=Path, help="WAV file to transcribe")
    args = parser.parse_args()
    if args.list:
        print(json.dumps({"models": list(SUPPORTED_MODELS)}, indent=2))
        return 0
    if not args.wav or not args.wav.is_file():
        print("error: --wav required and must exist", file=sys.stderr)
        return 2
    if args.model == "gigaam":
        text, sec = _transcribe_gigaam(args.wav)
        print(json.dumps({
            "model": args.model,
            "wav": str(args.wav),
            "text": text,
            "latency_s": round(sec, 3),
            "status": "scaffold",
        }, ensure_ascii=False))
        return 0
    print(json.dumps({
        "model": args.model,
        "status": "not_implemented",
        "hint": "Use MOSS_STT_PROVIDER + host STT for live bench",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
