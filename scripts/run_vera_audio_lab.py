#!/usr/bin/env python3
"""Stage B audio lab skeleton — blocked until owner accepts Stage A."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from golden_path.status import is_owner_accepted, status_line


def main() -> int:
    parser = argparse.ArgumentParser(description="Vera Golden Path audio lab (Stage B skeleton)")
    parser.add_argument("--input", type=Path, help="Input WAV file")
    parser.add_argument("--run-dir", type=Path, default=_REPO / "audio_lab_runs")
    args = parser.parse_args()

    print(status_line())
    if not is_owner_accepted():
        print("STATUS=BLOCKED_STAGE_A_OWNER_GATE")
        print(
            "Audio lab requires OWNER_ACCEPTED in docs/GOLDEN_PATH_STATUS.md "
            "after 10+ minutes in run_vera_text_lab.py"
        )
        return 2

    run_id = "blocked-stage-b"
    run_path = args.run_dir / run_id
    turn_path = run_path / "turn_1"
    turn_path.mkdir(parents=True, exist_ok=True)

    layout = {
        "pipeline": "WAV in → [NOT IMPLEMENTED: STT] → GoldenPathEngine → [NOT IMPLEMENTED: TTS] → WAV out",
        "input": str(args.input) if args.input else None,
        "turn_dir": str(turn_path),
        "files": [
            "input.wav",
            "stt.txt",
            "assistant.txt",
            "output.wav",
            "trace.json",
        ],
    }
    meta_path = turn_path / "trace.json"
    meta_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Stage B skeleton only — STT/TTS not implemented in this increment.")
    print(f"run_dir={run_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
