"""STT MLX worker — POST /v1/transcribe on port 9101."""

from __future__ import annotations

import base64
import os
import tempfile
import wave
from pathlib import Path
from typing import Any

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from services.inference.common import (
    InferenceExecutor,
    WorkerState,
    check_deadline,
    mount_health,
    new_request_id,
)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "voice-m5.yaml"


def _load_config() -> dict[str, Any]:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


class TranscribeRequest(BaseModel):
    request_id: str = Field(default_factory=new_request_id)
    call_id: str
    turn_id: int = 0
    utterance_id: str = ""
    sample_rate: int = 16000
    pcm_b64: str
    deadline: float | None = None


app = FastAPI(title="IMVERA STT Worker", version="0.1.0")
state = WorkerState()
executor = InferenceExecutor(max_queue=4)
_asr = None
_model_id = ""


def _pcm_to_wav(pcm: bytes, sample_rate: int, path: Path) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


def _transcribe_sync(wav_path: Path, language: str) -> dict[str, Any]:
    result = _asr.generate(str(wav_path), language=language)
    text = getattr(result, "text", "") or str(result)
    return {"text": text.strip(), "asr_quality": "GOOD"}


@app.on_event("startup")
def warmup() -> None:
    global _asr, _model_id
    cfg = _load_config()
    _model_id = cfg["models"]["asr"]["id"]
    try:
        from mlx_audio.stt import load

        _asr = load(_model_id)
        state.model_revision = _model_id
        state.ready = True
        # Smoke on tiny silence
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            _pcm_to_wav(b"\x00\x00" * 1600, 16000, Path(tmp.name))
            _transcribe_sync(Path(tmp.name), cfg["models"]["asr"]["language"])
            Path(tmp.name).unlink(missing_ok=True)
    except Exception as exc:
        state.warmup_error = str(exc)
        state.ready = False


mount_health(app, state, "stt")


@app.post("/v1/transcribe")
async def transcribe(req: TranscribeRequest) -> dict[str, Any]:
    if not state.ready or _asr is None:
        raise HTTPException(503, detail=state.warmup_error or "not ready")
    if req.request_id in state.cancelled_requests:
        raise HTTPException(499, detail="cancelled")
    check_deadline(req.deadline)
    try:
        pcm = base64.b64decode(req.pcm_b64)
    except Exception as exc:
        raise HTTPException(400, detail=f"invalid pcm_b64: {exc}") from exc
    if len(pcm) < 320:
        return {
            "request_id": req.request_id,
            "text": "",
            "asr_quality": "UNUSABLE",
            "duration_ms": 0,
            "model_revision": state.model_revision,
        }

    cfg = _load_config()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)
    _pcm_to_wav(pcm, req.sample_rate, wav_path)
    duration_ms = int(len(pcm) / 2 / req.sample_rate * 1000)
    try:
        result = await executor.run(
            lambda: _transcribe_sync(wav_path, cfg["models"]["asr"]["language"])
        )
    finally:
        wav_path.unlink(missing_ok=True)
    return {
        "request_id": req.request_id,
        "duration_ms": duration_ms,
        "model_revision": state.model_revision,
        **result,
    }


@app.post("/v1/cancel")
def cancel(body: dict[str, Any]) -> dict[str, str]:
    rid = body.get("request_id")
    if rid:
        state.cancelled_requests.add(rid)
    return {"status": "accepted"}


def main() -> None:
    cfg = _load_config()
    port = int(os.environ.get("IMVERA_STT_PORT", cfg["ports"]["stt"]))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
