#!/usr/bin/env python3
"""Download MOSS-TTS-Nano ONNX weights pinned to known-good revisions and
verify every file against the sha256 manifest (scripts/models.sha256).

Why pinned: the Docker image and all builds must be reproducible. The HF
repos can change at HEAD; this script locks the exact commit and refuses to
produce a tree that does not match the checksums the code was tested with.

Usage:
    python3 scripts/download_models.py [TARGET_DIR]
"""
import hashlib
import os
import sys
from pathlib import Path

TTS_REPO = "OpenMOSS-Team/MOSS-TTS-Nano-100M-ONNX"
CODEC_REPO = "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX"
TTS_REVISION = "f52645cb467506d8e18e746ddd59482685b74e58"
CODEC_REVISION = "ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae"

TTS_ALLOW = ("*.onnx", "*.data", "*.json", "tokenizer.model")
CODEC_ALLOW = ("*.onnx", "*.data", "*.json")


def _load_manifest(manifest: Path):
    expected = {}
    for line in manifest.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        digest, _, rel = line.partition("  ")
        expected[rel.strip()] = digest.strip()
    return expected


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _snapshot(repo_id: str, revision: str, target: Path, allow_patterns):
    from huggingface_hub import snapshot_download
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo_id,
        revision=revision,
        local_dir=str(target),
        allow_patterns=list(allow_patterns),
    )


def verify_manifest(root: Path, expected: dict) -> list:
    """Return a list of (rel, ok, msg) for every manifest entry."""
    bad = []
    for rel, digest in expected.items():
        p = root / rel
        if not p.is_file():
            bad.append((rel, False, "missing"))
            continue
        if _sha256(p) != digest:
            bad.append((rel, False, "sha256 mismatch"))
    return bad


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "runtime/models")
    manifest = Path(__file__).resolve().parent / "models.sha256"
    expected = _load_manifest(manifest)
    if not expected:
        print("manifest is empty:", manifest)
        return 2

    tts_dir = target / "MOSS-TTS-Nano-100M-ONNX"
    codec_dir = target / "MOSS-Audio-Tokenizer-Nano-ONNX"

    print(f"[models] downloading {TTS_REPO} @ {TTS_REVISION}")
    _snapshot(TTS_REPO, TTS_REVISION, tts_dir, TTS_ALLOW)
    print(f"[models] downloading {CODEC_REPO} @ {CODEC_REVISION}")
    _snapshot(CODEC_REPO, CODEC_REVISION, codec_dir, CODEC_ALLOW)

    bad = verify_manifest(target, expected)
    if bad:
        print("[models] FAILED:", flush=True)
        for rel, ok, msg in bad:
            print(f"  {rel}: {msg}", flush=True)
        return 1

    # drop HF download scaffolding; only ship the weights tree
    for d in (tts_dir, codec_dir):
        cache = d / ".cache"
        if cache.exists():
            import shutil
            shutil.rmtree(cache, ignore_errors=True)
    print(f"[models] OK — {len(expected)} files verified in {target}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())