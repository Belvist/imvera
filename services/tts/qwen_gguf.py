"""Portable HTTP client for the separately provisioned Qwen resident server.

Contract: /v1/audio/speech with response_format=pcm (s16le,24kHz).
The inference server's platform, weights and acceleration are deployment
artifacts, not dependencies of this client. Production failures remain failures;
explicit lab fallback policy belongs to the existing TTS worker.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from collections.abc import Callable, Iterator

import httpx

from services.inference.common import check_deadline
from services.inference.streaming import StreamCancelled

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
    with urllib.request.urlopen(f"{server_url()}/v1/models", timeout=timeout_s) as r:
        data = json.loads(r.read())
    return [m.get("id", "") for m in data.get("data", []) if m.get("id")]


def server_model_id(timeout_s: float = 10.0) -> str:
    """First model id the server reports (single-model server). Cached."""
    global _model_id
    if not _model_id:
        ids = list_models(timeout_s=timeout_s)
        if not ids:
            raise RuntimeError("qwen server reports no models")
        _model_id = ids[0]
    return _model_id


def list_voices(timeout_s: float = 10.0) -> list[str]:
    try:
        with urllib.request.urlopen(f"{server_url()}/v1/audio/voices", timeout=timeout_s) as r:
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
    body = json.dumps({"name": name, "ref_text": ref_text, "spk_b64": spk, "rvq_b64": rvq}).encode()
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
        with urllib.request.urlopen(f"{server_url()}/v1/models", timeout=timeout_s) as r:
            return r.status == 200
    except Exception:
        return False


def synthesize_stream(
    text: str,
    *,
    voice: str | None = None,
    lang: str = "Russian",
    cfg: dict | None = None,
    deadline: float | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> Iterator[bytes]:
    """Yield available PCM without waiting to fill a0.4s network buffer."""
    end = min(
        deadline if deadline is not None else float("inf"),
        time.monotonic() + TOTAL_TIMEOUT_S,
    )

    def remaining() -> float:
        if cancelled():
            raise StreamCancelled()
        check_deadline(end)
        return max(0.001, end - time.monotonic())

    try:
        model = server_model_id(timeout_s=min(10, remaining()))
    except (StreamCancelled, TimeoutError):
        raise
    except Exception as exc:
        raise RuntimeError(f"qwen-tts model list failed: {exc}") from exc
    body = {
        "model": model,
        "input": text,
        "voice": voice or qwen_voice(cfg or {}),
        "language": lang,
        "response_format": "pcm",
    }
    got = 0
    carry = b""
    try:
        timeout = httpx.Timeout(min(FIRST_BYTE_TIMEOUT_S, remaining()), connect=min(5, remaining()))
        with httpx.Client(timeout=timeout) as client:
            with client.stream(
                "POST",
                f"{server_url()}/v1/audio/speech",
                json=body,
                headers={"Accept-Encoding": "identity"},
            ) as response:
                response.raise_for_status()
                encoding = response.headers.get("content-encoding", "identity").lower()
                media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if encoding != "identity" or media_type not in {
                    "",
                    "application/octet-stream",
                    "audio/pcm",
                    "audio/l16",
                    "audio/raw",
                }:
                    raise RuntimeError("qwen-tts response is not raw PCM")
                packets = response.iter_raw()
                while True:
                    remaining()
                    try:
                        packet = next(packets)
                    except StopIteration:
                        break
                    remaining()
                    carry += packet
                    aligned = len(carry) // 2 * 2
                    if aligned:
                        chunk, carry = carry[:aligned], carry[aligned:]
                        got += len(chunk)
                        yield chunk
                remaining()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"qwen-tts request failed: {type(exc).__name__}") from exc
    if carry:
        raise RuntimeError("qwen-tts returned truncated PCM sample")
    if got == 0:
        raise RuntimeError("qwen-tts returned no audio")
