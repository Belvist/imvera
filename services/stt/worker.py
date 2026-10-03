"""STT worker — POST /v1/transcribe on port 9101 (GigaAM v3 lab default)."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from packages.contracts.stt import STT_PREVIEW_CHECKPOINTS_MS, STTCapabilities
from services.inference.common import (
    InferenceExecutor,
    QueueFullError,
    WorkerState,
    check_deadline,
    executor_http_error,
    mount_health,
    new_request_id,
)
from services.inference.config import load_worker_config, production_mode, worker_metadata
from services.inference.watchdog import (
    InferenceWatchdog,
    production_startup_guard,
    production_watchdog,
)
from services.stt.backends import load_asr_backend
from services.stt.critical_terms import match_critical_terms
from services.stt.normalize import normalize_transcript
from services.stt.quality import assess_asr_quality, pcm_rms_s16le
from services.stt.vocabulary import IMVERA_HOTWORDS

logger = logging.getLogger("stt.worker")

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "voice-m5.yaml"


def _load_config() -> dict[str, Any]:
    return load_worker_config(CONFIG_PATH, "stt")


class TranscribeRequest(BaseModel):
    request_id: str = Field(default_factory=new_request_id, min_length=1, max_length=160)
    call_id: str
    turn_id: int = 0
    utterance_id: str = ""
    sample_rate: int = Field(default=16000, gt=0, le=48000)
    # Bound memory before decoding, including callers outside the bridge.
    pcm_b64: str = Field(max_length=60 * 48000 * 2 * 4 // 3)
    deadline: float | None = Field(default=None, allow_inf_nan=False)
    # Relative budget: monotonic clocks on different worker hosts differ.
    timeout_s: float | None = Field(default=None, gt=0, le=60, allow_inf_nan=False)


class PreviewRequest(TranscribeRequest):
    partial_id: str = Field(min_length=1, max_length=160)
    timeout_s: float = Field(default=2.0, gt=0, le=2.0)


class _CancelledSTT(RuntimeError):
    pass


app = FastAPI(title="IMVERA STT Worker", version="0.2.0")
state = WorkerState()
executor = InferenceExecutor(max_queue=4)
_asr: Any = None
_asr_engine = "gigaam"
_model_id = ""
_watchdog: InferenceWatchdog | None = None
# Cancellation is scoped to this worker. Active requests carry an Event; early
# or late cancel messages retain only bounded, expiring tombstones so retries
# and disconnected callers cannot grow WorkerState forever.
_active_requests: dict[str, threading.Event] = {}
_cancelled_request_expiry: dict[str, float] = {}
_CANCEL_TTL_S = 60.0
_MAX_CANCEL_TOMBSTONES = 1024


def _prune_cancelled_requests(now: float) -> None:
    """Called only while holding state.lock."""
    for rid, expiry in tuple(_cancelled_request_expiry.items()):
        if expiry <= now:
            _cancelled_request_expiry.pop(rid, None)
            state.cancelled_requests.discard(rid)


def _register_request(request_id: str, cancelled: threading.Event) -> None:
    with state.lock:
        _prune_cancelled_requests(time.monotonic())
        if request_id in _active_requests:
            raise HTTPException(409, detail="request_id already active")
        if request_id in state.cancelled_requests:
            cancelled.set()
            state.cancelled_requests.discard(request_id)
            _cancelled_request_expiry.pop(request_id, None)
        _active_requests[request_id] = cancelled


def _release_request(request_id: str, cancelled: threading.Event) -> None:
    with state.lock:
        if _active_requests.get(request_id) is cancelled:
            _active_requests.pop(request_id, None)


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
    global _asr, _model_id, _asr_engine, _watchdog
    cfg = _load_config()
    state.runtime_metadata = worker_metadata(CONFIG_PATH)
    asr_cfg = cfg["models"]["asr"]
    _asr_engine = str(asr_cfg.get("engine", "gigaam"))
    try:
        with production_startup_guard(state, cfg):
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
        if production_mode():
            raise RuntimeError("selected production STT failed warmup") from exc
    _watchdog = production_watchdog(executor, state, cfg)


@app.on_event("shutdown")
def shutdown() -> None:
    state.ready = False
    with state.lock:
        for cancellation in _active_requests.values():
            cancellation.set()
    executor.shutdown()
    if _watchdog is not None:
        _watchdog.stop()


mount_health(app, state, "stt", executor_supplier=lambda: executor)


@app.get("/v1/capabilities")
def capabilities() -> dict[str, Any]:
    enabled = os.environ.get("IMVERA_STT_PREVIEW", "0") == "1"
    return STTCapabilities(
        partial_mode="prefix_batch" if enabled else "unsupported",
        preview_checkpoints_ms=STT_PREVIEW_CHECKPOINTS_MS if enabled else (),
        max_preview_duration_ms=STT_PREVIEW_CHECKPOINTS_MS[-1] if enabled else 0,
        model_revision=state.model_revision,
    ).model_dump()


@app.post("/v1/transcribe")
async def transcribe(req: TranscribeRequest) -> dict[str, Any]:
    return await _run_transcription(req, preview=False)


@app.post("/v1/preview")
async def preview(req: PreviewRequest) -> dict[str, Any]:
    if capabilities()["partial_mode"] != "prefix_batch":
        raise HTTPException(503, detail="prefix previews disabled; final-only worker")
    result = await _run_transcription(req, preview=True)
    return {
        "request_id": req.request_id,
        "partial_id": req.partial_id,
        "text": result["text"],
        "is_final": False,
        "partial_mode": "prefix_batch",
        "duration_ms": result["duration_ms"],
        "model_revision": result["model_revision"],
        "revisable": True,
    }


async def _run_transcription(
    req: TranscribeRequest,
    *,
    preview: bool,
) -> dict[str, Any]:
    if not state.ready or _asr is None:
        raise HTTPException(503, detail=state.warmup_error or "not ready")
    abandoned = threading.Event()
    cancelled = threading.Event()
    _register_request(req.request_id, cancelled)
    try:
        return await _run_registered_transcription(
            req,
            preview=preview,
            abandoned=abandoned,
            cancelled=cancelled,
        )
    finally:
        abandoned.set()
        _release_request(req.request_id, cancelled)


async def _run_registered_transcription(
    req: TranscribeRequest,
    *,
    preview: bool,
    abandoned: threading.Event,
    cancelled: threading.Event,
) -> dict[str, Any]:
    deadline = time.monotonic() + (req.timeout_s if req.timeout_s is not None else 60.0)
    if req.deadline is not None:
        deadline = min(deadline, req.deadline)

    def check_request() -> None:
        if abandoned.is_set() or cancelled.is_set():
            raise _CancelledSTT("cancelled")
        check_deadline(deadline)

    try:
        check_request()
    except _CancelledSTT as exc:
        raise HTTPException(499, detail="cancelled") from exc
    except TimeoutError as exc:
        raise executor_http_error(exc) from exc
    try:
        pcm = base64.b64decode(req.pcm_b64, validate=True)
    except Exception as exc:
        raise HTTPException(400, detail=f"invalid pcm_b64: {exc}") from exc
    if len(pcm) % 2:
        raise HTTPException(400, detail="pcm_s16le must contain complete 16-bit samples")
    if len(pcm) > 60 * req.sample_rate * 2:
        raise HTTPException(413, detail="transcription exceeds 60 second PCM limit")
    duration_ms = int(len(pcm) / 2 / req.sample_rate * 1000)
    if preview and len(pcm) not in {
        req.sample_rate * 2 * ms // 1000 for ms in STT_PREVIEW_CHECKPOINTS_MS
    }:
        raise HTTPException(422, detail="preview requires a bounded 1/2/4/8 second prefix")
    if len(pcm) < 320:
        return {
            "request_id": req.request_id,
            "is_final": True,
            "text": "",
            "asr_quality": "UNUSABLE",
            "duration_ms": 0,
            "model_revision": state.model_revision,
        }

    cfg = _load_config()

    def infer() -> dict[str, Any]:
        # The synchronous job owns the WAV even if HTTP is cancelled while
        # queued/running. Never unlink a file another thread still needs.
        check_request()
        with tempfile.TemporaryDirectory(prefix="imvera-stt-") as directory:
            wav_path = Path(directory) / "input.wav"
            _pcm_to_wav(pcm, req.sample_rate, wav_path)
            check_request()
            result = _transcribe_sync(
                wav_path,
                pcm=pcm,
                sample_rate=req.sample_rate,
                duration_ms=duration_ms,
                asr_cfg=cfg["models"]["asr"],
            )
            # In-flight model computation cannot be preempted; discard its
            # output rather than claim cancellation stopped CPU inference.
            check_request()
            return result

    try:
        check_request()
        # HTTP completion has its own wall-clock bound. A running model may
        # finish later; infer owns its WAV and abandoned discards that result.
        result = await asyncio.wait_for(
            executor.run(infer, idle_only=preview),
            timeout=max(0.0, deadline - time.monotonic()),
        )
    except _CancelledSTT as exc:
        raise HTTPException(499, detail="cancelled") from exc
    except (TimeoutError, QueueFullError) as exc:
        raise executor_http_error(exc) from exc
    pcm_rms = round(pcm_rms_s16le(pcm), 1)
    logger.info(
        "stt preview=%s call_id=%s utterance_id=%s duration_ms=%d pcm_rms=%.1f "
        "raw=%r text=%r quality=%s model=%s",
        preview,
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
        "is_final": not preview,
        "duration_ms": duration_ms,
        "pcm_rms": pcm_rms,
        "engine": _asr_engine,
        "model_revision": state.model_revision,
        **result,
    }


@app.post("/v1/cancel")
def cancel(body: dict[str, Any]) -> dict[str, str]:
    rid = body.get("request_id")
    if not isinstance(rid, str) or not rid or len(rid) > 160:
        raise HTTPException(422, detail="request_id must be a nonempty bounded string")
    with state.lock:
        now = time.monotonic()
        _prune_cancelled_requests(now)
        active = _active_requests.get(rid)
        if active is not None:
            active.set()
        else:
            if rid not in _cancelled_request_expiry:
                while len(_cancelled_request_expiry) >= _MAX_CANCEL_TOMBSTONES:
                    oldest = next(iter(_cancelled_request_expiry))
                    _cancelled_request_expiry.pop(oldest)
                    state.cancelled_requests.discard(oldest)
            state.cancelled_requests.add(rid)
            _cancelled_request_expiry[rid] = now + _CANCEL_TTL_S
    return {"status": "accepted"}


def main() -> None:
    global executor
    cfg = _load_config()
    executor = InferenceExecutor(max_queue=int(cfg.get("limits", {}).get("queue_depth", 4)))
    port = int(os.environ.get("IMVERA_STT_PORT", cfg["ports"]["stt"]))
    uvicorn.run(
        app,
        host=os.environ.get("IMVERA_WORKER_HOST", "127.0.0.1"),
        port=port,
        log_level="info",
        timeout_graceful_shutdown=25,
    )


if __name__ == "__main__":
    main()
