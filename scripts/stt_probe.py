#!/usr/bin/env python3
"""Probe live STT worker with wellness-critical phrases (ADR-003 mini-check)."""

from __future__ import annotations

import argparse
import base64
import json
import math
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "voice-m5.yaml"

# Wellness + safety phrases from ADR-003 / current-task call script.
PROBE_PHRASES: list[str] = [
    "всё хорошо",
    "все хорошо",
    "нормально",
    "не очень",
    "плохо",
    "да",
    "чувствую себя хорошо",
    "голова болит",
    "упала",
    "помогите",
    "скорая",
]


def _load_stt_url(override: str | None) -> str:
    if override:
        return override.rstrip("/")
    with CONFIG_PATH.open() as f:
        cfg = yaml.safe_load(f)
    port = cfg["ports"]["stt"]
    return f"http://127.0.0.1:{port}"


def _say_wav(phrase: str, sample_rate: int = 16000) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        aiff_path = Path(tmpdir) / "probe.aiff"
        wav_path = Path(tmpdir) / "probe.wav"
        subprocess.run(
            ["say", "-v", "Milena", "-o", str(aiff_path), phrase],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "afconvert",
                "-f",
                "WAVE",
                "-d",
                f"LEI16@{sample_rate}",
                str(aiff_path),
                str(wav_path),
            ],
            check=True,
            capture_output=True,
        )
        with wave.open(str(wav_path), "rb") as wf:
            return wf.readframes(wf.getnframes())


def _tone_wav(duration_ms: int, sample_rate: int = 16000) -> bytes:
    n = int(sample_rate * duration_ms / 1000)
    samples = [
        int(0.25 * 32767 * math.sin(2 * math.pi * 440.0 * i / sample_rate))
        for i in range(n)
    ]
    return struct.pack(f"<{len(samples)}h", *samples)


def _transcribe(base_url: str, pcm: bytes, sample_rate: int, label: str) -> dict:
    payload = {
        "call_id": "stt-probe",
        "turn_id": 0,
        "sample_rate": sample_rate,
        "pcm_b64": base64.b64encode(pcm).decode("ascii"),
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(f"{base_url}/v1/transcribe", json=payload)
        resp.raise_for_status()
        data = resp.json()
    data["probe_label"] = label
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="STT wellness phrase probe")
    parser.add_argument("--url", default=None, help="STT base URL (default from voice-m5.yaml)")
    parser.add_argument("--json", action="store_true", help="Print raw JSON lines")
    args = parser.parse_args(argv)

    base_url = _load_stt_url(args.url)
    try:
        with httpx.Client(timeout=5.0) as client:
            ready = client.get(f"{base_url}/health/ready")
            ready.raise_for_status()
            health = ready.json()
    except httpx.HTTPError as exc:
        print(f"STT not ready at {base_url}: {exc}", file=sys.stderr)
        return 1

    model_revision = str(health.get("model_revision", ""))
    if args.json:
        print(json.dumps({"stt_url": base_url, "model_revision": model_revision}, ensure_ascii=False))

    rows: list[dict] = []

    for phrase in PROBE_PHRASES:
        pcm = _say_wav(phrase)
        rows.append(_transcribe(base_url, pcm, 16000, f"say:{phrase}"))

    for duration_ms in (150, 500):
        pcm = _tone_wav(duration_ms)
        rows.append(_transcribe(base_url, pcm, 16000, f"tone:{duration_ms}ms"))

    if args.json:
        for row in rows:
            print(json.dumps(row, ensure_ascii=False))
        return 0

    print(f"STT probe @ {base_url}  model={model_revision or 'unknown'}\n")
    print(f"{'label':<28} {'text':<24} {'quality':<10} {'ms':>5}")
    print("-" * 72)
    for row in rows:
        text = str(row.get("text", ""))
        raw = row.get("raw_text")
        if raw and raw != text:
            text = f"{text} (raw:{raw})"
        print(
            f"{row.get('probe_label',''):<28} "
            f"{text:<24} "
            f"{str(row.get('asr_quality','')):<10} "
            f"{int(row.get('duration_ms', 0)):>5}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
