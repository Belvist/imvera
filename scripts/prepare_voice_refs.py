#!/usr/bin/env python3
"""Download or synthesize Russian female TTS reference clips + manifest."""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config" / "voice-m5.yaml"
OUT_DIR = ROOT / "config" / "voice_refs"
MANIFEST_PATH = OUT_DIR / "manifest.json"
TARGET_SR = 24000

BOOTSTRAP_PHRASES: dict[str, str] = {
    "vivian": (
        "Здравствуйте, меня зовут Вера. Я звоню, чтобы узнать, "
        "как вы себя чувствуете сегодня."
    ),
    "serena": (
        "Добрый день! Расскажите, пожалуйста, принимали ли вы лекарства утром, "
        "как обычно?"
    ),
}


def _normalize_wav(path: Path, target_sr: int = TARGET_SR) -> tuple[float, int]:
    """Re-encode to mono PCM16 at target sample rate via ffmpeg."""
    tmp = path.with_suffix(".tmp.wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(path),
        "-ac",
        "1",
        "-ar",
        str(target_sr),
        "-sample_fmt",
        "s16",
        str(tmp),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {path}: {proc.stderr[-500:]}")
    tmp.replace(path)
    data, sr = sf.read(path)
    dur = len(data) / sr
    return float(dur), int(sr)


def _write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> tuple[float, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    sf.write(path, arr, sample_rate, subtype="PCM_16")
    return _normalize_wav(path)


def synthesize_bootstrap(voice: str, text: str, out_path: Path) -> tuple[float, int]:
    from mlx_audio.tts.utils import load_model

    with CFG.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    model = load_model(cfg["models"]["tts"]["id"])
    chunks: list[np.ndarray] = []
    sample_rate = TARGET_SR
    for result in model.generate(
        text=text,
        voice=voice,
        lang_code="Russian",
        stream=False,
    ):
        chunks.append(np.asarray(result.audio, dtype=np.float32))
        sample_rate = int(result.sample_rate)
    audio = np.concatenate(chunks)
    return _write_wav(out_path, audio, sample_rate)


def download_fleurs_female(limit: int = 2) -> list[dict[str, Any]]:
    from datasets import Audio, load_dataset

    ds = load_dataset("google/fleurs", "ru_ru", split="train[:800]")
    ds = ds.cast_column("audio", Audio(decode=False))
    found: list[dict[str, Any]] = []
    for row in ds:
        if row.get("gender") != 0:
            continue
        raw = row["audio"]["bytes"]
        if not raw:
            continue
        data, sr = sf.read(io.BytesIO(raw))
        if data.ndim > 1:
            data = data.mean(axis=1)
        dur = len(data) / sr
        if not (4.0 <= dur <= 9.0):
            continue
        found.append(
            {
                "transcription": row["transcription"],
                "id": str(row["id"]),
                "data": data.astype(np.float32),
                "sr": sr,
            }
        )
        if len(found) >= limit:
            break
    if not found:
        raise RuntimeError("No suitable FLEURS ru_ru female clips found (4–9 s).")
    entries: list[dict[str, Any]] = []
    for idx, item in enumerate(found, start=1):
        ref_id = f"fleurs_ru_female_{idx}"
        out_path = OUT_DIR / f"{ref_id}.wav"
        dur, sr = _write_wav(out_path, item["data"], int(item["sr"]))
        entries.append(
            {
                "id": ref_id,
                "file": f"config/voice_refs/{ref_id}.wav",
                "ref_text": item["transcription"],
                "source": "google/fleurs ru_ru train split (speaker gender=female)",
                "source_url": "https://huggingface.co/datasets/google/fleurs",
                "license": "CC-BY-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "attribution": "Speech from FLEURS Russian (Google, CC BY 4.0)",
                "speaker_gender": "female",
                "language": "ru",
                "duration_s": round(dur, 2),
                "sample_rate_hz": sr,
                "kind": "human",
                "recommended": idx == 1,
                "fleurs_id": item["id"],
            }
        )
    return entries


def build_manifest(
    fleurs_entries: list[dict[str, Any]],
    bootstrap_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    refs = fleurs_entries + bootstrap_entries
    default_ref = "fleurs_ru_female_1"
    if not any(r["id"] == default_ref for r in refs):
        default_ref = refs[0]["id"] if refs else None
    return {
        "version": 1,
        "default_ref": default_ref,
        "notes": (
            "Zero-shot refs for Qwen3-TTS CustomVoice (not trained voices). "
            "Replace bootstrap entries with licensed talent recordings before production."
        ),
        "refs": refs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-fleurs",
        action="store_true",
        help="Only synthesize bootstrap refs (offline / no datasets download).",
    )
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="Only download human FLEURS refs.",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fleurs_entries: list[dict[str, Any]] = []
    bootstrap_entries: list[dict[str, Any]] = []

    if not args.skip_fleurs:
        print("Downloading FLEURS ru_ru female clips (CC-BY-4.0)...")
        try:
            fleurs_entries = download_fleurs_female(limit=2)
            for e in fleurs_entries:
                print(f"  {e['id']}: {e['duration_s']}s — {e['ref_text'][:60]}...")
        except Exception as exc:
            print(f"Warning: FLEURS download failed ({exc}). Bootstrap-only mode.", file=sys.stderr)

    if not args.skip_bootstrap:
        print("Synthesizing bootstrap refs from Qwen presets...")
        for voice, text in BOOTSTRAP_PHRASES.items():
            ref_id = f"bootstrap_{voice}_ru"
            out_path = OUT_DIR / f"{ref_id}.wav"
            dur, sr = synthesize_bootstrap(voice, text, out_path)
            bootstrap_entries.append(
                {
                    "id": ref_id,
                    "file": f"config/voice_refs/{ref_id}.wav",
                    "ref_text": text,
                    "source": (
                        "Synthesized with mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit "
                        f"preset {voice}"
                    ),
                    "license": "project-bootstrap",
                    "license_url": None,
                    "attribution": "IMVERA lab bootstrap — replace before production",
                    "speaker_gender": "female",
                    "language": "ru",
                    "duration_s": round(dur, 2),
                    "sample_rate_hz": sr,
                    "kind": "bootstrap",
                    "recommended": False,
                }
            )
            print(f"  {ref_id}: {dur:.2f}s")

    if not fleurs_entries and not bootstrap_entries:
        print("No references produced.", file=sys.stderr)
        return 1

    manifest = build_manifest(fleurs_entries, bootstrap_entries)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    n = len(manifest["refs"])
    print(f"Wrote {MANIFEST_PATH} ({n} refs, default={manifest['default_ref']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
