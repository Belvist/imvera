#!/usr/bin/env python3
"""Preview TTS output — direct MLX, Silero lab, or via running worker."""

from __future__ import annotations

import argparse
import base64
import json
import sys
import uuid
from pathlib import Path

import httpx

from services.tts.preview import synthesize_preview
from services.tts.voice_refs import load_manifest

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config" / "voice-m5.yaml"
DEFAULT_TEXT = "Вера на связи. Скажите, пожалуйста, как вы спали этой ночью?"


def preview_worker(text: str, worker_url: str, out_path: Path) -> None:
    payload = {
        "call_id": "preview",
        "generation_id": str(uuid.uuid4()),
        "phrase_id": "preview-1",
        "text": text,
    }
    pcm_chunks: list[bytes] = []
    sample_rate = 24000
    with httpx.Client(timeout=120.0) as client:
        with client.stream("POST", f"{worker_url.rstrip('/')}/v1/synthesize", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                item = json.loads(line)
                if item.get("done"):
                    if item.get("error"):
                        raise RuntimeError(item["error"])
                    break
                sample_rate = int(item.get("sample_rate", sample_rate))
                pcm_chunks.append(base64.b64decode(item["pcm_b64"]))

    import numpy as np
    import soundfile as sf

    if not pcm_chunks:
        raise RuntimeError("worker returned no audio")
    pcm = b"".join(pcm_chunks)
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32767.0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_path, audio, sample_rate, subtype="PCM_16")
    print(f"wrote {out_path} ({len(audio)/sample_rate:.2f}s @ {sample_rate}Hz) via worker")


def list_refs() -> None:
    manifest = load_manifest(CFG)
    print(f"default_ref: {manifest.get('default_ref')}")
    for entry in manifest.get("refs", []):
        mark = "*" if entry.get("recommended") else " "
        print(
            f"{mark} {entry['id']:24} {entry.get('kind','?'):10} "
            f"{entry.get('license','?'):16} {entry.get('duration_s')}s"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default=DEFAULT_TEXT, help="Russian phrase to synthesize")
    parser.add_argument("--ref-id", help="Manifest ref id (enables clone for this preview)")
    parser.add_argument("--preset", help="Override preset voice when not cloning")
    parser.add_argument("--no-ref", action="store_true", help="Force preset mode (no clone)")
    parser.add_argument("--engine", choices=["mlx_customvoice", "mlx_base_clone", "silero_lab"])
    parser.add_argument("--temperature", type=float, help="Override sampling temperature")
    parser.add_argument("--out", type=Path, default=Path("/tmp/imvera_tts_preview.wav"))
    parser.add_argument("--worker", help="Use running TTS worker URL instead of direct MLX")
    parser.add_argument("--list-refs", action="store_true", help="List manifest refs and exit")
    args = parser.parse_args()

    if args.list_refs:
        list_refs()
        return 0

    try:
        if args.worker:
            preview_worker(args.text, args.worker, args.out)
        else:
            mode = synthesize_preview(
                args.text,
                args.out,
                ref_id=args.ref_id,
                preset=args.preset,
                use_ref=False if args.no_ref else None,
                engine=args.engine,
                temperature=args.temperature,
            )
            import soundfile as sf

            info = sf.info(args.out)
            print(f"{mode}")
            print(f"wrote {args.out} ({info.duration:.2f}s @ {info.samplerate}Hz)")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
