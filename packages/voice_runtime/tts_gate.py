"""TTS warmup and call gate helpers."""

from __future__ import annotations

import json
import time

import httpx


def measure_tts_first_pcm_s(
    tts_url: str = "http://127.0.0.1:9102",
    *,
    budget_read_s: float = 90.0,
) -> float:
    started = time.monotonic()
    timeout = httpx.Timeout(5.0, read=budget_read_s)
    with httpx.Client(timeout=timeout) as client:
        with client.stream(
            "POST",
            f"{tts_url.rstrip('/')}/v1/synthesize",
            json={
                "call_id": "gate-warmup",
                "generation_id": "gate-warm",
                "phrase_id": "gate-p",
                "text": "Здравствуйте.",
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
                    return time.monotonic() - started
    return 0.0
