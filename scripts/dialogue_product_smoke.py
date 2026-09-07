#!/usr/bin/env python3
"""Product dialogue smoke — verify stack before Zoiper call."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _check(url: str, label: str) -> None:
    try:
        r = httpx.get(url, timeout=3.0)
        r.raise_for_status()
        print(f"OK  {label}: {url}")
    except httpx.HTTPError as exc:
        print(f"FAIL {label}: {url} ({exc})")
        raise SystemExit(1) from exc


def main() -> int:
    stt = os.environ.get("IMVERA_STT_URL", "http://127.0.0.1:9101")
    tts = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    llm = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    gw = os.environ.get("IMVERA_VOICE_GATEWAY_HTTP", "http://127.0.0.1:9200")

    print("=== IMVERA dialogue product smoke ===\n")
    _check(f"{gw}/health/ready", "voice gateway")
    _check(f"{stt}/health/ready", "STT")
    _check(f"{tts}/health/ready", "TTS")
    _check(f"{llm}/health/ready", "LLM")

    print("\n--- policy + CallActor gates ---")
    subprocess.check_call(
        ["make", "test-dialogue-gates"],
        cwd=ROOT,
    )

    print("\n--- live LLM (optional) ---")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pytest", "tests/test_llm_live_dialogue.py", "-v"],
            cwd=ROOT,
        )
    except subprocess.CalledProcessError:
        print("WARN live LLM tests failed or skipped — Zoiper may still work via rule fallback")

    print("\nREADY: dial Zoiper extension 7000 (make zoiper-info)")
    print("Trace: .run/traces/<call_id>.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
