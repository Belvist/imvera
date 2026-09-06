#!/usr/bin/env python3
"""Download pinned MLX model weights into local cache."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config" / "voice-m5.yaml"


def main() -> int:
    with CFG.open() as f:
        cfg = yaml.safe_load(f)
    models = [
        cfg["models"]["asr"]["id"],
        cfg["models"]["llm"]["id"],
        cfg["models"]["tts"]["id"],
    ]
    for model_id in models:
        print(f"Preparing {model_id}...")
        code = subprocess.call(
            [sys.executable, "-m", "huggingface_hub.cli", "download", model_id],
        )
        if code != 0:
            print(
                f"BLOCKED: failed to download {model_id}. "
                "Install huggingface_hub and ensure network access.",
                file=sys.stderr,
            )
            return code
    print("Models prepared.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
