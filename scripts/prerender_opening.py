#!/usr/bin/env python3
"""Pre-render opening wellness phrase via TTS — instant playback on first Zoiper call."""

from __future__ import annotations

import base64
import json
import os
import sys

import httpx

from packages.dialogue.planner import Planner
from packages.dialogue.state import DialogueState
from packages.voice_runtime.opening_cache import save_opening

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _opening_text(elder_name: str) -> str:
    state = DialogueState(
        call_id="prerender",
        family_id="fam-voice",
        elder_display_name=elder_name,
    )
    return Planner._opening_wellness_speech(state)


def main() -> int:
    tts_url = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102").rstrip("/")
    elder = os.environ.get("IMVERA_ELDER_DISPLAY_NAME", "Даниил")
    text = _opening_text(elder)

    try:
        r = httpx.get(f"{tts_url}/health/ready", timeout=3.0)
        if r.status_code != 200:
            print(f"BLOCKED: TTS not ready ({r.status_code})", file=sys.stderr)
            return 1
        engine = str(r.json().get("model_revision", "")).strip()
    except httpx.HTTPError as exc:
        print(f"BLOCKED: TTS unreachable: {exc}", file=sys.stderr)
        return 1
    if "macos_say" in engine or not engine.startswith("silero_lab:silero:"):
        print(f"BLOCKED: TTS is not Silero Xenia ({engine!r})", file=sys.stderr)
        return 1
    os.environ["IMVERA_TTS_MODEL_REVISION"] = engine

    pcm_parts: list[bytes] = []
    sample_rate = 24000
    timeout = httpx.Timeout(5.0, read=30.0)
    with httpx.Client(timeout=timeout) as client:
        with client.stream(
            "POST",
            f"{tts_url}/v1/synthesize",
            json={
                "call_id": "prerender",
                "generation_id": "prerender-g",
                "phrase_id": "prerender-p",
                "text": text,
            },
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if data.get("done"):
                    break
                if data.get("pcm_b64"):
                    pcm_parts.append(base64.b64decode(data["pcm_b64"]))
                    sample_rate = int(data.get("sample_rate", sample_rate))

    pcm = b"".join(pcm_parts)
    if not pcm:
        print("BLOCKED: prerender produced no PCM", file=sys.stderr)
        return 1

    path = save_opening(text, pcm, sample_rate, engine=engine)
    print(f"Opening cached: {path.name} ({len(pcm)} bytes @ {sample_rate} Hz engine={engine})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
