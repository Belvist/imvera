"""Offline synthetic voice selection for Apple Silicon; never modifies the live stack.

Audio generation requires the real MLX models. No fallback or placeholder audio.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.metadata
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DESIGN_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit"
CLONE_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_real_model(model_id, revision):
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("Generation requires Apple Silicon macOS with MLX. No audio was generated.")
    import mlx.core as mx
    from huggingface_hub import HfApi, snapshot_download
    from mlx_audio.tts.utils import load_model

    # Resolve once, then load that exact immutable model revision.
    resolved = HfApi().model_info(model_id, revision=revision).sha
    if not resolved:
        raise RuntimeError("Cannot resolve model revision")
    snapshot = snapshot_download(repo_id=model_id, revision=resolved)
    model = load_model(Path(snapshot))
    metadata = {
        "model_id": model_id, "model_revision": resolved,
        "mlx_audio_version": importlib.metadata.version("mlx-audio"),
        "mlx_version": importlib.metadata.version("mlx"),
        "platform": platform.platform(), "model_license_declared": "Apache-2.0",
    }
    return model, mx, metadata


def save_generated(results, wav_path):
    import numpy as np
    import soundfile as sf

    arrays, rate = [], None
    for result in results:
        current_rate = int(result.sample_rate)
        if rate is not None and current_rate != rate:
            raise ValueError("Sample rate changed during generation")
        rate = current_rate
        audio = np.asarray(result.audio, dtype=np.float32)
        if audio.ndim == 2 and 1 in audio.shape:
            audio = audio.reshape(-1)
        if audio.ndim != 1 or not np.isfinite(audio).all():
            raise ValueError("Expected finite mono audio")
        arrays.append(audio)
    if not arrays or rate != 24000:
        raise ValueError(f"Expected real 24000 Hz output, received rate={rate}")
    audio = np.concatenate(arrays)
    if len(audio) < rate // 2:
        raise ValueError("Empty or implausibly short output")
    peak = float(np.max(np.abs(audio)))
    if peak < 0.001:
        raise ValueError("Output is effectively silent")
    # Only attenuate to avoid clipping. Never upsample or amplify quiet material.
    gain = min(1.0, (10 ** (-1 / 20)) / peak)
    audio = audio * gain
    sf.write(str(wav_path), audio, rate, subtype="PCM_16", format="WAV")
    return {
        "sample_rate": rate, "channels": 1, "subtype": "PCM_16",
        "samples": len(audio), "duration_seconds": len(audio) / rate,
        "raw_peak": peak, "gain_applied": gain,
        "rms": float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))),
        "audio_sha256": sha256(wav_path),
    }


def write_gallery(out, rows):
    cards = []
    for row in rows:
        cards.append(
            '<article><h2>' + html.escape(row["label"]) + '</h2><p>'
            + html.escape(row["speaker_id"] + ' / ' + row["take_id"]) + '</p>'
            + '<audio controls preload="none" src="' + html.escape(row["audio"]) + '"></audio>'
            + '<p>' + html.escape(row["expected_text"]) + '</p></article>'
        )
    document = '<!doctype html><html lang="ru"><meta charset="utf-8"><title>IMVERA — голоса</title>'
    document += '<style>body{font:17px system-ui;max-width:900px;margin:40px auto;padding:20px;background:#f7f5ef;color:#172822}article{background:white;border-radius:16px;padding:20px;margin:18px 0}audio{width:100%}h2{font-size:20px}</style>'
    document += '<h1>IMVERA — кандидаты голоса</h1><p>Синтетические образцы. Оцените произношение, полноту фразы и естественность. Одинаковое описание не гарантирует одинаковый тембр.</p>'
    document += ''.join(cards) + '</html>'
    (out / "listen.html").write_text(document, encoding="utf-8")


def design(args):
    catalog = read_json(ROOT / "profiles.json")
    profiles = catalog["profiles"][:args.limit]
    out = Path(args.out).resolve()
    if out.exists():
        raise FileExistsError("Choose a new output directory; existing takes are preserved")
    model, mx, metadata = load_real_model(args.model, args.revision)
    if model.config.tts_model_type != "voice_design":
        raise ValueError("design requires a VoiceDesign checkpoint")
    out.mkdir(parents=True)
    rows, errors = [], []
    for index, profile in enumerate(profiles):
        for take in range(1, args.takes + 1):
            take_id = f"{profile['id']}_take{take:02d}"
            seed = args.seed + index * 1000 + take
            mx.random.seed(seed)
            started = time.monotonic()
            wav = out / f"{take_id}.wav"
            try:
                results = model.generate_voice_design(
                    text=catalog["reference_text"], language="Russian",
                    instruct=profile["description"], stream=False, max_tokens=1024,
                )
                metrics = save_generated(results, wav)
                row = {
                    **metadata, **metrics, "speaker_id": profile["id"],
                    "label": profile["label"], "description": profile["description"],
                    "take_id": take_id, "audio": wav.name,
                    "expected_text": catalog["reference_text"], "language": "Russian",
                    "seed": seed, "source_type": "synthetic_voice_design",
                    "qa_status": "unreviewed", "generation_seconds": time.monotonic() - started,
                }
                write_json(out / f"{take_id}.json", row)
                rows.append(row)
                print(f"Generated {take_id}: {metrics['duration_seconds']:.1f}s; listening review required", flush=True)
            except (RuntimeError, ValueError, OSError) as exc:
                errors.append({"take_id": take_id, "error": str(exc)})
                print(f"FAILED {take_id}: {exc}", file=sys.stderr, flush=True)
    write_json(out / "manifest.json", {"clips": rows, "errors": errors})
    write_gallery(out, rows)
    if errors:
        raise RuntimeError(f"{len(errors)} generations failed; see manifest.json")


def clone(args):
    ref_path = Path(args.reference).resolve()
    ref = read_json(ref_path)
    if ref.get("qa_status") != "approved" or not ref.get("verified_transcript", "").strip():
        raise ValueError("Listen to a candidate; set qa_status=approved and verified_transcript to the words actually spoken")
    wav = ref_path.parent / ref["audio"]
    if sha256(wav) != ref["audio_sha256"]:
        raise ValueError("Reference WAV changed after review")
    out = Path(args.out).resolve()
    if out.exists():
        raise FileExistsError("Choose a new output directory")
    model, mx, metadata = load_real_model(args.model, args.revision)
    if model.config.tts_model_type != "base":
        raise ValueError("Reference cloning requires a Base checkpoint, not CustomVoice")
    out.mkdir(parents=True)
    rows = []
    for index, item in enumerate(read_json(args.texts)):
        seed = args.seed + index
        mx.random.seed(seed)
        target = out / f"{index + 1:02d}_{item['id']}.wav"
        started = time.monotonic()
        metrics = save_generated(model.generate(
            text=item["text"], lang_code="Russian", ref_audio=str(wav),
            ref_text=ref["verified_transcript"], stream=False, max_tokens=1024,
        ), target)
        row = {
            **metadata, **metrics, "audio": target.name,
            "speaker_id": ref["speaker_id"], "label": ref["label"], "take_id": item["id"],
            "reference_audio_sha256": ref["audio_sha256"], "expected_text": item["text"],
            "source_type": "synthetic_reference_clone", "qa_status": "unreviewed",
            "seed": seed, "generation_seconds": time.monotonic() - started,
        }
        rows.append(row)
        write_json(out / (target.stem + ".json"), row)
        write_json(out / "manifest.json", {"clips": rows})
        print(f"Generated {target.name}", flush=True)
    write_gallery(out, rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="Show profiles; no downloads or generation")
    d = sub.add_parser("design", help="Generate real VoiceDesign candidate WAVs on a Mac")
    d.add_argument("--out", required=True)
    d.add_argument("--takes", type=int, choices=range(1, 5), default=2)
    d.add_argument("--limit", type=int, choices=range(1, 13), default=12)
    d.add_argument("--model", default=DESIGN_MODEL)
    d.add_argument("--revision", default="main")
    d.add_argument("--seed", type=int, default=20260906)
    c = sub.add_parser("clone", help="Evaluate a selected reference with fresh text")
    c.add_argument("--reference", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--texts", default=str(ROOT / "evaluation_texts.json"))
    c.add_argument("--model", default=CLONE_MODEL)
    c.add_argument("--revision", default="main")
    c.add_argument("--seed", type=int, default=20260906)
    args = parser.parse_args()
    if args.command == "plan":
        print(json.dumps(read_json(ROOT / "profiles.json"), ensure_ascii=False, indent=2))
    elif args.command == "design":
        design(args)
    else:
        clone(args)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, ImportError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
