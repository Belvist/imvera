"""TTS MLX worker — NDJSON streaming on port 9102."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import queue
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.inference.cancellation import CancellationRegistry, DuplicateRequestError
from services.inference.common import (
    InferenceExecutor,
    QueueFullError,
    WorkerState,
    check_deadline,
    executor_http_error,
    mount_health,
    new_request_id,
)
from services.inference.config import (
    load_worker_config,
    production_mode,
    worker_metadata,
    worker_profile_path,
)
from services.inference.streaming import BoundedInferenceStream, StreamCancelled
from services.inference.watchdog import (
    InferenceWatchdog,
    production_startup_guard,
    production_watchdog,
)
from services.tts.gen_params import build_mlx_gen_kwargs, resolve_model_id, tts_engine
from services.tts.sentence_stream import sentence_segments
from services.tts.silero_lab import (
    SILERO_WARNING,
    lab_backend_name,
    synthesize_silero,
)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "voice-m5.yaml"
_tts = None
_cancellations = CancellationRegistry()
_watchdog: InferenceWatchdog | None = None
_dependency_probe_lock = threading.Lock()


def _load_config() -> dict[str, Any]:
    return load_worker_config(CONFIG_PATH, "tts")


def _is_cancelled(req: SynthesizeRequest) -> bool:
    return _cancellations.is_cancelled(req.request_id, req.generation_id)


class SynthesizeRequest(BaseModel):
    request_id: str = Field(default_factory=new_request_id, min_length=1, max_length=160)
    call_id: str = Field(min_length=1, max_length=160)
    generation_id: str = Field(min_length=1, max_length=160)
    phrase_id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=2000)
    voice: str | None = Field(default=None, max_length=160)
    language: str | None = Field(default=None, max_length=32)
    deadline: float | None = Field(default=None, allow_inf_nan=False)
    timeout_ms: int | None = Field(default=None, gt=0, le=120000)


class CancelRequest(BaseModel):
    generation_id: str | None = Field(default=None, min_length=1, max_length=160)
    request_id: str | None = Field(default=None, min_length=1, max_length=160)


app = FastAPI(title="IMVERA TTS Worker", version="0.1.0")
state = WorkerState()
executor = InferenceExecutor(max_queue=4)


def _float_to_pcm16(audio: np.ndarray) -> bytes:
    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    arr = np.clip(arr, -1.0, 1.0)
    return (arr * 32767.0).astype(np.int16).tobytes()


def _chunk_pcm(pcm: bytes, sample_rate: int, frame_ms: int = 160) -> list[tuple[bytes, int]]:
    """Slice PCM into ~frame_ms chunks for streaming contract."""
    frame_samples = max(1, int(sample_rate * frame_ms / 1000))
    frame_bytes = frame_samples * 2
    chunks: list[tuple[bytes, int]] = []
    for offset in range(0, len(pcm), frame_bytes):
        chunks.append((pcm[offset : offset + frame_bytes], sample_rate))
    if not chunks:
        chunks.append((b"", sample_rate))
    return chunks


def _produce_silero_chunks(
    req: SynthesizeRequest, out_q: queue.Queue, tts_cfg: dict[str, Any]
) -> None:
    silero_cfg = dict(tts_cfg.get("silero_lab") or {})
    seq = 0
    try:
        segments = (
            sentence_segments(req.text)
            if os.environ.get("IMVERA_TTS_SENTENCE_STREAM", "0") == "1"
            else [req.text]
        )
        for segment in segments:
            if _is_cancelled(req):
                break
            check_deadline(req.deadline)
            audio, sample_rate = synthesize_silero(segment, silero_cfg)
            pcm = _float_to_pcm16(audio)
            for chunk_pcm, sr in _chunk_pcm(pcm, sample_rate):
                if _is_cancelled(req):
                    break
                out_q.put(
                    {
                        "sequence": seq,
                        "sample_rate": sr,
                        "pcm_b64": base64.b64encode(chunk_pcm).decode("ascii"),
                        "is_last": False,
                    }
                )
                seq += 1
    finally:
        out_q.put(None)


def _produce_mlx_chunks(
    req: SynthesizeRequest, out_q: queue.Queue, tts_cfg: dict[str, Any]
) -> None:
    if _tts is None:
        raise RuntimeError("TTS model not loaded")
    voice = req.voice or tts_cfg["voice"]
    lang = req.language or tts_cfg["lang_code"]
    gen_kwargs, ref_id = build_mlx_gen_kwargs(
        tts_cfg,
        worker_profile_path(CONFIG_PATH),
        text=req.text,
        voice=voice,
        lang_code=lang,
        stream=True,
    )
    if ref_id:
        print(f"TTS clone ref={ref_id} temp={gen_kwargs.get('temperature')}")
    elif gen_kwargs.get("instruct"):
        print(f"TTS preset voice={voice} instruct=on temp={gen_kwargs.get('temperature')}")
    else:
        print(f"TTS preset voice={voice} temp={gen_kwargs.get('temperature')}")

    seq = 0
    try:
        for result in _tts.generate(**gen_kwargs):
            if _is_cancelled(req):
                break
            audio = getattr(result, "audio", None)
            if audio is None:
                continue
            pcm = _float_to_pcm16(np.asarray(audio))
            sample_rate = int(getattr(result, "sample_rate", 24000))
            out_q.put(
                {
                    "sequence": seq,
                    "sample_rate": sample_rate,
                    "pcm_b64": base64.b64encode(pcm).decode("ascii"),
                    "is_last": False,
                }
            )
            seq += 1
    finally:
        out_q.put(None)


class _QwenStreamFailure(RuntimeError):
    def __init__(self, reason: str, emitted_chunks: int) -> None:
        super().__init__(f"Qwen stream failed after {emitted_chunks} PCM chunks: {reason}")
        self.emitted_chunks = emitted_chunks


def _produce_qwen_chunks(
    req: SynthesizeRequest, out_q: queue.Queue, tts_cfg: dict[str, Any]
) -> int:
    """Qwen GGUF primary via resident server. Returns chunk count, raises
    on failure, sends NO sentinel (caller owns it for fallback control)."""
    from services.tts.qwen_gguf import QWEN_SAMPLE_RATE, synthesize_stream

    seq = 0
    try:
        for pcm in synthesize_stream(
            req.text,
            voice=req.voice,
            lang=req.language or "Russian",
            cfg=tts_cfg,
            deadline=req.deadline,
            cancelled=lambda: _is_cancelled(req),
        ):
            if _is_cancelled(req):
                break
            for chunk_pcm, sr in _chunk_pcm(pcm, QWEN_SAMPLE_RATE):
                out_q.put(
                    {
                        "sequence": seq,
                        "sample_rate": sr,
                        "pcm_b64": base64.b64encode(chunk_pcm).decode("ascii"),
                        "is_last": False,
                    }
                )
                seq += 1
    except (StreamCancelled, TimeoutError):
        raise
    except Exception as exc:
        raise _QwenStreamFailure(str(exc), seq) from exc
    return seq


def _produce_chunks(req: SynthesizeRequest, out_q: queue.Queue) -> None:
    cfg = _load_config()
    tts_cfg = cfg["models"]["tts"]
    engine = tts_engine(tts_cfg)
    if engine == "silero_lab":
        _produce_silero_chunks(req, out_q, tts_cfg)
    elif engine == "qwen_gguf":
        reason = "no audio generated"
        try:
            produced = _produce_qwen_chunks(req, out_q, tts_cfg)
        except (StreamCancelled, TimeoutError):
            raise
        except Exception as exc:
            _verify_qwen_readiness()
            if isinstance(exc, _QwenStreamFailure) and exc.emitted_chunks > 0:
                print(
                    f"TTS actual_engine=qwen_gguf status=failed_after_pcm "
                    f"call_id={req.call_id} generation_id={req.generation_id} "
                    f"phrase_id={req.phrase_id}: {exc}",
                    flush=True,
                )
                out_q.put({"done": True, "error": str(exc)})
                out_q.put(None)
                return
            produced = 0
            reason = str(exc)
        if produced == 0 and not _is_cancelled(req):
            if production_mode():
                out_q.put({"done": True, "error": f"selected TTS failed: {reason}"})
                out_q.put(None)
                return
            # Fallback is permitted only before any Qwen PCM was emitted.
            print(
                f"TTS requested_engine=qwen_gguf actual_engine=silero_lab "
                f"call_id={req.call_id} generation_id={req.generation_id} "
                f"phrase_id={req.phrase_id} fallback_reason={reason}",
                flush=True,
            )
            _produce_silero_chunks(req, out_q, tts_cfg)
        else:
            out_q.put(None)
    else:
        _produce_mlx_chunks(req, out_q, tts_cfg)


MLX_LOAD_TIMEOUT_S = float(os.environ.get("IMVERA_TTS_MLX_LOAD_TIMEOUT_S", "120"))


def _init_silero_lab(tts_cfg: dict[str, Any]) -> bool:
    """Load Silero for lab; set IMVERA_TTS_ENGINE so runtime routes stay consistent."""
    try:
        from services.tts.silero_lab import load_silero

        load_silero(tts_cfg.get("silero_lab") or {})
        state.model_revision = f"silero_lab:{lab_backend_name(tts_cfg.get('silero_lab') or {})}"
        if "macos_say" in state.model_revision:
            state.ready = False
            state.warmup_error = "macos_say is not Silero Xenia"
            print("BLOCKED: TTS macos_say — install .[lab-silero] / torch", flush=True)
            return False
        state.ready = True
        state.warmup_error = None
        os.environ["IMVERA_TTS_ENGINE"] = "silero_lab"
        print(f"WARNING: {SILERO_WARNING}", flush=True)
        return True
    except Exception as exc:
        state.warmup_error = str(exc)
        state.ready = False
        print(f"TTS silero_lab init failed: {exc}", flush=True)
        return False


def _load_mlx_model(model_id: str, timeout_s: float) -> tuple[Any | None, str | None]:
    """load_model in a thread — avoids indefinite hang blocking HTTP bind."""
    box: dict[str, Any] = {"model": None, "error": None}

    def _run() -> None:
        try:
            from mlx_audio.tts.utils import load_model

            box["model"] = load_model(model_id)
        except Exception as exc:
            box["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout_s)
    if thread.is_alive():
        return None, f"load_model timeout after {timeout_s:.0f}s"
    if box["error"] is not None:
        return None, str(box["error"])
    if box["model"] is None:
        return None, f"load_model returned None for {model_id}"
    return box["model"], None


def _qwen_warmup_failure(tts_cfg: dict[str, Any], reason: str) -> None:
    if production_mode():
        state.ready = False
        state.warmup_error = reason
        print(f"TTS startup_failed selected_engine=qwen_gguf error={reason[:200]}", flush=True)
        return
    print(f"TTS {reason} — explicit lab fallback to silero", flush=True)
    _init_silero_lab(tts_cfg)


def _ping_and_warmup_qwen(tts_cfg: dict[str, Any]) -> None:
    """Ping resident qwen server + warmup phrase; explicit owner-blessed
    fallback to silero (loud log — never silent). The removed generic
    MLX fallback stays removed; qwen's fallback is explicit per owner
    order, not a hidden provider."""
    state.ready = False
    try:
        from services.tts.qwen_gguf import ensure_voice_registered, ping, qwen_voice
        from services.tts.warmup import warmup_synthesis

        if not ping():
            _qwen_warmup_failure(tts_cfg, "qwen server unreachable")
            return
        from services.tts.qwen_gguf import server_model_id

        if not ensure_voice_registered(qwen_voice(tts_cfg)):
            _qwen_warmup_failure(tts_cfg, "qwen voice missing")
            return
        selected_revision = f"qwen_gguf:{server_model_id()}"

        def produce_selected(req: SynthesizeRequest, out_q: queue.Queue) -> None:
            try:
                _produce_qwen_chunks(req, out_q, tts_cfg)
            finally:
                out_q.put(None)

        # Probe the selected provider; per-request fallback cannot prove it ready.
        first_s = warmup_synthesis(produce_selected, text="А.", timeout_s=180.0)
        if first_s <= 0:
            _qwen_warmup_failure(tts_cfg, "qwen warmup produced no audio")
            return
        print(f"TTS qwen warmup first chunk in {first_s:.2f}s", flush=True)
        state.model_revision = selected_revision
        state.warmup_error = None
        state.ready = True
    except Exception as exc:
        _qwen_warmup_failure(tts_cfg, f"qwen warmup failed: {exc}")


@app.on_event("startup")
def startup() -> None:
    global _watchdog
    cfg = _load_config()
    state.runtime_metadata = worker_metadata(CONFIG_PATH)
    tts_cfg = cfg["models"]["tts"]
    if tts_engine(tts_cfg) == "silero_lab":
        _init_silero_lab(tts_cfg)
    _watchdog = production_watchdog(
        executor, state, cfg, drained=lambda: _cancellations.stats()["active"] == 0
    )
    # MLX load+warmup runs on the process main thread before HTTP binds (see main()).


def _load_and_warmup_mlx(tts_cfg: dict[str, Any], engine: str) -> None:
    global _tts
    model_id = resolve_model_id(tts_cfg)
    try:
        from services.tts.warmup import warmup_synthesis

        print(f"TTS loading {model_id} (timeout {MLX_LOAD_TIMEOUT_S:.0f}s)...", flush=True)
        loaded, err = _load_mlx_model(model_id, MLX_LOAD_TIMEOUT_S)
        if loaded is None:
            state.warmup_error = err or "load failed"
            state.ready = False
            return
        _tts = loaded
        state.model_revision = f"{engine}:{model_id}"
        first_s = warmup_synthesis(_produce_chunks, text="А.", timeout_s=180.0)
        if first_s <= 0:
            state.warmup_error = "warmup synthesis produced no audio"
            state.ready = False
            return
        print(f"TTS warmup first chunk in {first_s:.2f}s", flush=True)
        state.ready = True
    except Exception as exc:
        state.warmup_error = str(exc)
        state.ready = False
        print(f"TTS load/warmup failed: {exc}", flush=True)


@app.on_event("shutdown")
def shutdown() -> None:
    state.ready = False
    _cancellations.cancel_all_active()
    executor.shutdown()
    if _watchdog is not None:
        _watchdog.stop()


def _verify_qwen_readiness() -> bool:
    """Warmup is historical; check the production resident without generating.

    A lost registry needs the existing bootstrap/voice registration again.
    A changed model fails closed for operator review, rather than blessing
    a different model by automatically warming a restarted client.
    """
    if not production_mode():
        return state.ready
    cfg = _load_config()
    tts_cfg = cfg["models"]["tts"]
    if tts_engine(tts_cfg) != "qwen_gguf":
        return state.ready
    with _dependency_probe_lock:
        if not state.ready:
            return False
        from services.tts.qwen_gguf import list_models, list_voices, qwen_voice

        reason = "qwen resident unavailable"
        changed_model = False
        try:
            models = list_models(timeout_s=0.4)
            accepted_model = state.model_revision.removeprefix("qwen_gguf:")
            if models and accepted_model not in models:
                reason = "qwen resident model changed; operator review required"
                changed_model = True
            elif models and qwen_voice(tts_cfg) in list_voices(timeout_s=0.4):
                return True
            elif models:
                reason = "qwen resident lost accepted voice registration"
        except Exception:
            # Errors must not turn a dependency outage into a green health.
            reason = "qwen resident readiness probe failed"
        state.ready = False
        state.warmup_error = reason
        if _watchdog is not None and not changed_model:
            _watchdog.request_restart(reason)
        return False


mount_health(
    app,
    state,
    "tts",
    executor_supplier=lambda: executor,
    details_supplier=lambda: {"cancellation": _cancellations.stats()},
    readiness_check=_verify_qwen_readiness,
)


def _prepare_stream(req: SynthesizeRequest) -> BoundedInferenceStream:
    lease = _cancellations.register(req.request_id, req.generation_id)
    try:
        return BoundedInferenceStream(
            executor,
            lambda out_q: _produce_chunks(req, out_q),
            deadline=req.deadline,
            cancelled=lease.cancelled.is_set,
            on_close=lease.cancelled.set,
            on_settled=lambda: _cancellations.release(lease),
        )
    except BaseException:
        _cancellations.release(lease)
        raise


class _InferenceResponse(StreamingResponse):
    def __init__(self, req: SynthesizeRequest, stream: BoundedInferenceStream) -> None:
        super().__init__(_ndjson_stream(req, stream), media_type="application/x-ndjson")
        self._inference_stream = stream
        self._deadline = req.deadline

    async def __call__(self, scope, receive, send) -> None:
        try:
            remaining = (
                None if self._deadline is None else max(0, self._deadline - time.monotonic())
            )
            # Includes blocked ASGI socket writes, not only queue/model waits.
            async with asyncio.timeout(remaining):
                await super().__call__(scope, receive, send)
        finally:
            # Also handles disconnect before body iteration/header send.
            self._inference_stream.close()


async def _ndjson_stream(
    req: SynthesizeRequest,
    stream: BoundedInferenceStream,
) -> AsyncIterator[bytes]:
    got_audio = False
    try:
        async for item in stream.items():
            if item.get("done"):
                yield (json.dumps(item, ensure_ascii=False) + "\n").encode()
                return
            got_audio = True
            yield (json.dumps(item, ensure_ascii=False) + "\n").encode()
    except StreamCancelled:
        yield (json.dumps({"done": True, "cancelled": True}) + "\n").encode()
        return
    except Exception as exc:
        yield (json.dumps({"done": True, "error": str(exc) or type(exc).__name__}) + "\n").encode()
        return
    finally:
        stream.close()
    if not got_audio and not _is_cancelled(req):
        yield (
            json.dumps({"done": True, "error": "no audio generated"}, ensure_ascii=False) + "\n"
        ).encode()
        return
    yield (json.dumps({"done": True}) + "\n").encode()


@app.post("/v1/synthesize")
async def synthesize(req: SynthesizeRequest) -> StreamingResponse:
    cfg = _load_config()
    engine = tts_engine(cfg["models"]["tts"])
    # qwen_gguf carries no in-process model (_tts stays None by design —
    # the resident server is the model, proven at warmup).
    if engine != "silero_lab" and engine != "qwen_gguf" and (not state.ready or _tts is None):
        raise HTTPException(503, detail=state.warmup_error or "not ready")
    if engine == "qwen_gguf" and not state.ready:
        raise HTTPException(503, detail=state.warmup_error or "qwen not ready")
    if engine == "silero_lab" and not state.ready:
        raise HTTPException(503, detail=state.warmup_error or "silero lab not ready")
    if req.timeout_ms is not None:
        req = req.model_copy(update={"deadline": time.monotonic() + req.timeout_ms / 1000})
    else:
        budget = min(float(cfg.get("limits", {}).get("tts_deadline_s", 20)), 120)
        req = req.model_copy(
            update={
                "deadline": min(
                    req.deadline if req.deadline is not None else time.monotonic() + budget,
                    time.monotonic() + 120,
                )
            }
        )
    try:
        stream = _prepare_stream(req)
    except StreamCancelled as exc:
        raise HTTPException(499, detail="cancelled") from exc
    except DuplicateRequestError as exc:
        raise HTTPException(409, detail="request_id already active") from exc
    except (TimeoutError, QueueFullError) as exc:
        raise executor_http_error(exc) from exc
    return _InferenceResponse(req, stream)


@app.post("/v1/cancel")
def cancel(body: CancelRequest) -> dict[str, str]:
    if body.generation_id is None and body.request_id is None:
        raise HTTPException(422, detail="cancellation requires request_id or generation_id")
    _cancellations.cancel(request_id=body.request_id, generation_id=body.generation_id)
    return {"status": "accepted"}


def main() -> None:
    global executor
    cfg = _load_config()
    executor = InferenceExecutor(max_queue=int(cfg.get("limits", {}).get("queue_depth", 4)))
    port = int(os.environ.get("IMVERA_TTS_PORT", cfg["ports"]["tts"]))
    tts_cfg = cfg["models"]["tts"]
    engine = tts_engine(tts_cfg)
    with production_startup_guard(state, cfg):
        if engine == "qwen_gguf":
            _ping_and_warmup_qwen(tts_cfg)
        elif engine != "silero_lab":
            _load_and_warmup_mlx(tts_cfg, engine)
    if production_mode() and not state.ready:
        raise SystemExit(70)
    uvicorn.run(
        app,
        host=os.environ.get("IMVERA_WORKER_HOST", "127.0.0.1"),
        port=port,
        log_level="info",
        timeout_graceful_shutdown=25,
    )


if __name__ == "__main__":
    main()
