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
DEFAULT_VOICE = "vera_kseniya"

FIRST_BYTE_TIMEOUT_S = float(os.environ.get("IMVERA_QWEN_TTS_FIRST_TIMEOUT_S", "20"))
TOTAL_TIMEOUT_S = float(os.environ.get("IMVERA_QWEN_TTS_TOTAL_TIMEOUT_S", "120"))

_model_id: str | None = None


def server_url() -> str:
    return os.environ.get("IMVERA_QWEN_TTS_URL", "http://127.0.0.1:8899").rstrip("/")


def qwen_voice(cfg: dict) -> str:
    return (
        os.environ.get("IMVERA_QWEN_TTS_VOICE")
        or str((cfg.get("qwen_gguf") or {}).get("voice") or DEFAULT_VOICE)
    ).strip() or DEFAULT_VOICE


def _models_dir() -> str:
    return os.environ.get(
        "IMVERA_QWEN_GGUF_DIR",
        os.path.join(os.getcwd(), "models", "qwen3_tts_gguf"),
    )


def list_models(timeout_s: float = 10.0) -> list[str]:
    with urllib.request.urlopen(
        f"{server_url()}/v1/models", timeout=timeout_s
    ) as r:
        data = json.loads(r.read())
    return [m.get("id", "") for m in data.get("data", []) if m.get("id")]


def server_model_id() -> str:
    """First model id the server reports (single-model server). Cached."""
    global _model_id
    if not _model_id:
        ids = list_models()
        if not ids:
            raise RuntimeError("qwen server reports no models")
        _model_id = ids[0]
    return _model_id


def list_voices(timeout_s: float = 10.0) -> list[str]:
    try:
        with urllib.request.urlopen(
            f"{server_url()}/v1/audio/voices", timeout=timeout_s
        ) as r:
            data = json.loads(r.read())
        voices = data.get("voices") or data.get("data") or []
        return [v.get("name", "") if isinstance(v, dict) else v for v in voices]
    except Exception:
        return []


def ensure_voice_registered(name: str = DEFAULT_VOICE) -> bool:
    """Idempotent clone registration (server registry is in-memory —
    re-register after every server restart). Returns True when usable."""
    import base64

    if name in list_voices():
        return True
    d = _models_dir()
    try:
        with open(os.path.join(d, f"{name}.spk"), "rb") as f:
            spk = base64.b64encode(f.read()).decode()
        with open(os.path.join(d, f"{name}.rvq"), "rb") as f:
            rvq = base64.b64encode(f.read()).decode()
        with open(os.path.join(d, f"{name}_ref.txt")) as f:
            ref_text = f.read()
    except OSError:
        return False
    body = json.dumps(
        {"name": name, "ref_text": ref_text, "spk_b64": spk, "rvq_b64": rvq}
    ).encode()
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                f"{server_url()}/v1/audio/voices",
                data=body,
                headers={"Content-Type": "application/json"},
            ),
            timeout=30.0,
        ):
            pass
        return True
    except Exception:
        return False


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
    try:
        model = server_model_id()
    except Exception as exc:
        raise RuntimeError(f"qwen-tts model list failed: {exc}") from exc
    body = json.dumps(
        {
            "model": model,
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
