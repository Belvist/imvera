#!/usr/bin/env python3
"""Helper to list/record human WAV prompts for black-box SIP gate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tests" / "assets" / "blackbox_voice" / "manifest.json"
WAV_DIR = ROOT / "tests" / "assets" / "blackbox_voice" / "wav"


def _load() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def cmd_list() -> int:
    data = _load()
    prompts = data.get("prompts") or {}
    phrases = data.get("phrases") or {}
    for pid in sorted(phrases):
        text = prompts.get(pid, "(add prompt text to manifest.json)")
        print(f"{pid}\t{text}")
    return 0


def cmd_record(phrase_id: str) -> int:
    data = _load()
    phrases = data.get("phrases") or {}
    if phrase_id not in phrases:
        print(f"unknown phrase_id: {phrase_id}", file=sys.stderr)
        return 1
    prompts = data.get("prompts") or {}
    text = prompts.get(phrase_id)
    if not text:
        print(f"no prompt text for {phrase_id} in manifest.json", file=sys.stderr)
        return 1
    WAV_DIR.mkdir(parents=True, exist_ok=True)
    out = WAV_DIR / Path(phrases[phrase_id]).name
    aiff = out.with_suffix(".aiff")
    print(f"Recording: {text}")
    subprocess.run(["say", "-v", "Milena", text, "-o", str(aiff)], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(aiff), "-ac", "1", "-ar", "16000", str(out)],
        check=True,
    )
    aiff.unlink(missing_ok=True)
    print(f"Wrote {out}")
    print("NOTE: replace with real human recording for production acceptance.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Black-box voice asset recorder")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--record", metavar="PHRASE_ID")
    args = parser.parse_args()
    if args.list:
        return cmd_list()
    if args.record:
        return cmd_record(args.record)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
