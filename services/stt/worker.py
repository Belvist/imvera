"""STT worker — POST /v1/transcribe on port 9101 (GigaAM v3 lab default)."""

from __future__ import annotations

import base64
import logging
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
from services.stt.backends import load_asr_backend
from services.stt.critical_terms import match_critical_terms
from services.stt.normalize import normalize_transcript
from services.stt.quality import assess_asr_quality, pcm_rms_s16le
from services.stt.vocabulary import IMVERA_HOTWORDS

logger = logging.getLogger("stt.worker")

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


app = FastAPI(title="IMVERA STT Worker", version="0.2.0")
state = WorkerState()
executor = InferenceExecutor(max_queue=4)
_asr: Any = None
_asr_engine = "gigaam"
_model_id = ""


def _pcm_to_wav(pcm: bytes, sample_rate: int, path: Path) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


def _transcribe_sync(
    wav_path: Path,
    *,
    pcm: bytes,
    sample_rate: int,
    duration_ms: int,
    asr_cfg: dict[str, Any],
) -> dict[str, Any]:
    hotwords = IMVERA_HOTWORDS if str(asr_cfg.get("engine", "gigaam")) == "mlx_qwen" else None
    if hotwords is not None:
        raw_text = _asr.transcribe_wav(wav_path, hotwords=hotwords)
    else:
        try:
            raw_text = _asr.transcribe_wav(wav_path)
        except ValueError as exc:
            # Over the ~25s single-pass limit (slow elderly speech): fall
            # back to windowed longform instead of HTTP 500.
            if "Too long" not in str(exc) or not hasattr(_asr, "transcribe_wav_longform"):
                raise
            logger.info("stt longform fallback duration_ms=%d", duration_ms)
            raw_text = _asr.transcribe_wav_longform(wav_path)
    text = normalize_transcript(raw_text)
    quality = assess_asr_quality(
        pcm,
        sample_rate=sample_rate,
        duration_ms=duration_ms,
        text=raw_text,
        generation_tokens=None,
    )
    pcm_rms = round(pcm_rms_s16le(pcm), 1)
    return {
        "text": text,
        "raw_text": raw_text,
        "asr_quality": quality,
        "pcm_rms": pcm_rms,
        "generation_tokens": None,
        "critical_terms": match_critical_terms(text),
    }


@app.on_event("startup")
def warmup() -> None:
    global _asr, _model_id, _asr_engine
    cfg = _load_config()
    asr_cfg = cfg["models"]["asr"]
    _asr_engine = str(asr_cfg.get("engine", "gigaam"))
    try:
        _asr, _model_id = load_asr_backend(asr_cfg)
        state.model_revision = _model_id
        state.ready = True
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)
        silence = b"\x00\x00" * 1600
        _pcm_to_wav(silence, 16000, wav_path)
        try:
            _transcribe_sync(
                wav_path,
                pcm=silence,
                sample_rate=16000,
                duration_ms=100,
                asr_cfg=asr_cfg,
            )
        finally:
            wav_path.unlink(missing_ok=True)
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
            lambda: _transcribe_sync(
                wav_path,
                pcm=pcm,
                sample_rate=req.sample_rate,
                duration_ms=duration_ms,
                asr_cfg=cfg["models"]["asr"],
            )
        )
    finally:
        wav_path.unlink(missing_ok=True)
    pcm_rms = round(pcm_rms_s16le(pcm), 1)
    logger.info(
        "stt call_id=%s utterance_id=%s duration_ms=%d pcm_rms=%.1f "
        "raw=%r text=%r quality=%s model=%s",
        req.call_id,
        req.utterance_id or "-",
        duration_ms,
        pcm_rms,
        result.get("raw_text", ""),
        result.get("text", ""),
        result.get("asr_quality", ""),
        state.model_revision,
    )
    return {
        "request_id": req.request_id,
        "duration_ms": duration_ms,
        "pcm_rms": pcm_rms,
        "engine": _asr_engine,
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
