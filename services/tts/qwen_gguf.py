"""Qwen3-TTS GGUF provider (qwentts.cpp resident server, Metal).

Primary expressive voice; Silero stays as the instant fallback (the
worker routes there on any error — never a failed call). Server runs
separately (launchd ai.imvera.qwen-tts, :8899) so model load (~17s) and
Metal init happen once, not per phrase. Contract: OpenAI-compatible
/v1/audio/speech with response_format=pcm (s16le stream, 24 kHz).
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Iterator

QWEN_SAMPLE_RATE = 24000

FIRST_BYTE_TIMEOUT_S = float(os.environ.get("IMVERA_QWEN_TTS_FIRST_TIMEOUT_S", "20"))
TOTAL_TIMEOUT_S = float(os.environ.get("IMVERA_QWEN_TTS_TOTAL_TIMEOUT_S", "120"))


def server_url() -> str:
    return os.environ.get("IMVERA_QWEN_TTS_URL", "http://127.0.0.1:8899").rstrip("/")


def qwen_voice(cfg: dict) -> str:
    return (
        os.environ.get("IMVERA_QWEN_TTS_VOICE")
        or str((cfg.get("qwen_gguf") or {}).get("voice") or "serena")
    ).strip() or "serena"


def ping(timeout_s: float = 5.0) -> bool:
    try:
        with urllib.request.urlopen(
            f"{server_url()}/v1/models", timeout=timeout_s
        ) as r:
            return r.status == 200
    except Exception:
        return False


def synthesize_stream(
    text: str, *, voice: str | None = None, lang: str = "Russian", cfg: dict | None = None
) -> Iterator[bytes]:
    """Yield s16le PCM chunks (24 kHz). Raises on any failure (caller falls back)."""
    body = json.dumps(
        {
            "model": "qwen-talker-0.6b-customvoice-Q8_0.gguf",
            "input": text,
            "voice": voice or qwen_voice(cfg or {}),
            "language": lang,
            "response_format": "pcm",
        }
    ).encode()
    req = urllib.request.Request(
        f"{server_url()}/v1/audio/speech",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=TOTAL_TIMEOUT_S)
    except Exception as exc:
        raise RuntimeError(f"qwen-tts request failed: {exc}") from exc
    if resp.status != 200:
        raise RuntimeError(f"qwen-tts status {resp.status}")
    got = 0
    try:
        while True:
            chunk = resp.read(19200)  # ~0.4 s of 24 kHz s16le
            if not chunk:
                break
            got += len(chunk)
            yield chunk
    finally:
        try:
            resp.close()
        except Exception:
            pass
    if got == 0:
        raise RuntimeError("qwen-tts returned no audio")
