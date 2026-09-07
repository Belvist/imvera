#!/usr/bin/env python3
"""Download pinned voice model weights into local cache."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config" / "voice-m5.yaml"


def _prepare_vad() -> None:
    vad_path = ROOT / "config" / "models" / "silero_vad.onnx"
    vad_path.parent.mkdir(parents=True, exist_ok=True)
    if vad_path.exists():
        return
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


def _prepare_asr(asr_cfg: dict) -> int:
    engine = str(asr_cfg.get("engine", "gigaam")).strip().lower()
    if engine == "gigaam":
        from services.stt.gigaam_engine import ensure_gigaam_artifacts

        model_id = str(asr_cfg.get("id", "v3_e2e_rnnt"))
        download_root_raw = asr_cfg.get("download_root")
        download_root = Path(download_root_raw).expanduser() if download_root_raw else None
        print(f"Preparing GigaAM {model_id}...")
        try:
            ensure_gigaam_artifacts(model_id, download_root)
        except Exception as exc:
            print(f"BLOCKED: GigaAM download failed ({model_id}): {exc}", file=sys.stderr)
            return 1
        return 0

    if engine == "mlx_qwen":
        model_id = str(asr_cfg["id"])
        print(f"Preparing MLX ASR {model_id}...")
        try:
            from huggingface_hub import snapshot_download

            snapshot_download(model_id)
        except Exception as exc:
            print(f"BLOCKED: failed to download {model_id}: {exc}", file=sys.stderr)
            return 1
        return 0

    print(f"BLOCKED: unknown ASR engine {engine!r}", file=sys.stderr)
    return 1


def main() -> int:
    with CFG.open() as f:
        cfg = yaml.safe_load(f)

    _prepare_vad()

    if _prepare_asr(cfg["models"]["asr"]) != 0:
        return 1

    for model_id in (cfg["models"]["llm"]["id"], cfg["models"]["tts"]["id"]):
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
