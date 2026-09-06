#!/usr/bin/env python3
"""Preview TTS output — direct MLX or via running worker."""

from __future__ import annotations

import argparse
import base64
import json
import sys
import uuid
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config" / "voice-m5.yaml"
DEFAULT_TEXT = "Вера на связи. Скажите, пожалуйста, как вы спали этой ночью?"


def _load_cfg() -> dict:
    with CFG.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def preview_direct(
    text: str,
    ref_id: str | None,
    preset: str | None,
    out_path: Path,
) -> None:
    import numpy as np
    import soundfile as sf
    from mlx_audio.tts.utils import load_model

    from services.tts.voice_refs import resolve_tts_ref

    cfg = _load_cfg()
    tts_cfg = dict(cfg["models"]["tts"])
    if ref_id:
        tts_cfg["ref_id"] = ref_id
    if preset:
        tts_cfg["voice"] = preset

    ref_path, ref_text, resolved_id = resolve_tts_ref(tts_cfg, CFG)
    voice = preset or tts_cfg.get("voice", "vivian")

    gen_kwargs: dict = {
        "text": text,
        "voice": voice,
        "lang_code": tts_cfg.get("lang_code", "Russian"),
        "stream": False,
    }
    if ref_path is not None and ref_text:
        gen_kwargs["ref_audio"] = str(ref_path)
        gen_kwargs["ref_text"] = ref_text
        print(f"clone ref={resolved_id or ref_path.name}")
    else:
        print(f"preset voice={voice}")

    model = load_model(tts_cfg["id"])
    chunks = []
    sr = 24000
    for result in model.generate(**gen_kwargs):
        chunks.append(np.asarray(result.audio, dtype=np.float32))
        sr = int(result.sample_rate)
    audio = np.concatenate(chunks)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_path, audio, sr, subtype="PCM_16")
    print(f"wrote {out_path} ({len(audio)/sr:.2f}s @ {sr}Hz)")


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
    from services.tts.voice_refs import load_manifest

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
    parser.add_argument("--ref-id", help="Manifest ref id (default from config/manifest)")
    parser.add_argument("--preset", help="Override preset voice when not cloning")
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
            preview_direct(args.text, args.ref_id, args.preset, args.out)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
