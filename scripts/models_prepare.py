#!/usr/bin/env python3
"""Download pinned MLX model weights into local cache."""

from __future__ import annotations

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
    vad_path = ROOT / "config" / "models" / "silero_vad.onnx"
    vad_path.parent.mkdir(parents=True, exist_ok=True)
    if not vad_path.exists():
        print("Preparing silero_vad.onnx...")
        try:
            from huggingface_hub import hf_hub_download

            hf_hub_download(
                "deepghs/silero-vad-onnx",
                "silero_vad.onnx",
                local_dir=str(vad_path.parent),
            )
        except Exception as exc:
            print(f"Warning: silero VAD download failed ({exc}) — energy VAD fallback.")
    for model_id in models:
        print(f"Preparing {model_id}...")
        try:
            from huggingface_hub import snapshot_download

            snapshot_download(model_id)
        except Exception as exc:
            print(
                f"BLOCKED: failed to download {model_id}: {exc}",
                file=sys.stderr,
            )
            return 1
    print("Models prepared.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
