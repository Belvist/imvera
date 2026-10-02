#!/usr/bin/env python3
"""Product dialogue smoke — verify stack before Zoiper call."""

from __future__ import annotations

import os
import subprocess

import httpx

from services.providers.replica_pool import split_urls

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _check(url: str, label: str) -> dict:
    try:
        r = httpx.get(url, timeout=3.0)
        r.raise_for_status()
        payload = r.json()
        if not isinstance(payload, dict):
            raise ValueError("readiness payload must be an object")
        print(f"OK  {label}: {url}")
        return payload
    except (httpx.HTTPError, ValueError) as exc:
        print(f"FAIL {label}: {url} ({exc})")
        raise SystemExit(1) from exc


def main() -> int:
    stt = os.environ.get("IMVERA_STT_URL", "http://127.0.0.1:9101")
    tts = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    bridge = os.environ.get(
        "IMVERA_MEDIA_BRIDGE_HTTP",
        f"http://127.0.0.1:{os.environ.get('IMVERA_MEDIA_BRIDGE_PORT', '9210')}",
    ).rstrip("/")

    print("=== IMVERA dialogue product smoke ===\n")
    truth = _check(f"{bridge}/health/ready", "FreeSWITCH CallActor bridge")
    dialogue = truth.get("dialogue") or {}
    if (
        truth.get("mode") != "callactor"
        or not isinstance(dialogue, dict)
        or dialogue.get("dialogue.engine.enabled") is not True
        or dialogue.get("dialogue.engine.mode") != "single_writer"
    ):
        print("FAIL bridge must run the single-writer DialogueEngine CallActor path")
        raise SystemExit(1)
    for name, configured in (("stt", stt), ("tts", tts)):
        try:
            selected_urls = split_urls(configured)
            bridge_urls = split_urls(str(truth.get(name) or ""))
        except ValueError as exc:
            print(f"FAIL {name.upper()} configuration is missing: {exc}")
            raise SystemExit(1) from exc
        if selected_urls != bridge_urls:
            print(f"FAIL {name.upper()} smoke endpoints differ from the active bridge")
            raise SystemExit(1)
        for index, base_url in enumerate(selected_urls, 1):
            _check(f"{base_url}/health/ready", f"{name.upper()} replica {index}")

    print("\n--- policy + CallActor gates ---")
    subprocess.check_call(
        ["make", "test-dialogue-gates"],
        cwd=ROOT,
    )

    print("\nPREFLIGHT passed: dial Zoiper extension 7000 (make zoiper-info)")
    print("NOT VERIFIED: live SIP audio, audible interruption and turn latency")
    print("Trace: .run/traces/<call_id>.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
