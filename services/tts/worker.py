"""TTS MLX worker — NDJSON streaming on port 9102."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import queue
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import numpy as np
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.inference.common import (
    InferenceExecutor,
    QueueFullError,
    WorkerState,
    check_deadline,
    executor_http_error,
    mount_health,
    new_request_id,
)
from services.tts.gen_params import build_mlx_gen_kwargs, resolve_model_id, tts_engine
from services.tts.silero_lab import (
    SILERO_WARNING,
    lab_backend_name,
    synthesize_silero,
)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "voice-m5.yaml"
_tts = None
_cancelled: set[str] = set()


def _load_config() -> dict[str, Any]:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


class SynthesizeRequest(BaseModel):
    request_id: str = Field(default_factory=new_request_id)
    call_id: str
    generation_id: str
    phrase_id: str
    text: str = Field(min_length=1, max_length=2000)
    voice: str | None = None
    language: str | None = None
    deadline: float | None = None


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
        audio, sample_rate = synthesize_silero(req.text, silero_cfg)
        pcm = _float_to_pcm16(audio)
        for chunk_pcm, sr in _chunk_pcm(pcm, sample_rate):
            if req.generation_id in _cancelled:
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
        CONFIG_PATH,
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
            if req.generation_id in _cancelled:
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
        ):
            if req.generation_id in _cancelled:
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
        except Exception as exc:
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
        if produced == 0 and req.generation_id not in _cancelled:
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
            print("TTS qwen server unreachable — explicit fallback to silero", flush=True)
            _init_silero_lab(tts_cfg)
            return
        from services.tts.qwen_gguf import server_model_id

        if not ensure_voice_registered(qwen_voice(tts_cfg)):
            print("TTS qwen voice missing — explicit fallback to silero", flush=True)
            _init_silero_lab(tts_cfg)
            return
        state.model_revision = f"qwen_gguf:{server_model_id()}"

        def produce_selected(req: SynthesizeRequest, out_q: queue.Queue) -> None:
            try:
                _produce_qwen_chunks(req, out_q, tts_cfg)
            finally:
                out_q.put(None)

        # Probe the selected provider; per-request fallback cannot prove it ready.
        first_s = warmup_synthesis(produce_selected, text="А.", timeout_s=180.0)
        if first_s <= 0:
            print("TTS qwen warmup produced no audio — explicit fallback to silero", flush=True)
            _init_silero_lab(tts_cfg)
            return
        print(f"TTS qwen warmup first chunk in {first_s:.2f}s", flush=True)
        state.model_revision = "qwen_gguf:qwen-talker-0.6b-customvoice-Q8_0"
        state.warmup_error = None
        state.ready = True
    except Exception as exc:
        print(f"TTS qwen warmup failed ({exc}) — explicit fallback to silero", flush=True)
        _init_silero_lab(tts_cfg)


@app.on_event("startup")
def startup() -> None:
    cfg = _load_config()
    tts_cfg = cfg["models"]["tts"]
    if tts_engine(tts_cfg) == "silero_lab":
        _init_silero_lab(tts_cfg)
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


mount_health(app, state, "tts")


async def _ndjson_stream(req: SynthesizeRequest) -> AsyncIterator[bytes]:
    try:
        check_deadline(req.deadline)
    except (TimeoutError, QueueFullError) as exc:
        raise executor_http_error(exc) from exc
    out_q: queue.Queue = queue.Queue(maxsize=8)

    def produce() -> None:
        _produce_chunks(req, out_q)

    try:
        fut = executor.submit(produce)
    except QueueFullError as exc:
        # Raised before the first byte: fail over cleanly with 429.
        raise executor_http_error(exc) from exc
    got_audio = False
    try:
        while True:
            item = await asyncio.to_thread(out_q.get)
            if item is None:
                break
            if req.generation_id in _cancelled:
                yield (json.dumps({"done": True, "cancelled": True}) + "\n").encode()
                return
            if item.get("done"):
                yield (json.dumps(item, ensure_ascii=False) + "\n").encode()
                return
            got_audio = True
            yield (json.dumps(item, ensure_ascii=False) + "\n").encode()
    finally:
        await asyncio.wrap_future(fut)
    if not got_audio and req.generation_id not in _cancelled:
        yield (
            json.dumps({"done": True, "error": "no audio generated"}, ensure_ascii=False)
            + "\n"
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
    if executor.queue_depth >= 4:
        raise HTTPException(503, detail="inference queue full")
    return StreamingResponse(_ndjson_stream(req), media_type="application/x-ndjson")


@app.post("/v1/cancel")
def cancel(body: dict[str, Any]) -> dict[str, str]:
    gid = body.get("generation_id")
    if gid:
        _cancelled.add(gid)
    rid = body.get("request_id")
    if rid:
        state.cancelled_requests.add(rid)
    return {"status": "accepted"}


def main() -> None:
    cfg = _load_config()
    port = int(os.environ.get("IMVERA_TTS_PORT", cfg["ports"]["tts"]))
    tts_cfg = cfg["models"]["tts"]
    engine = tts_engine(tts_cfg)
    if engine == "qwen_gguf":
        _ping_and_warmup_qwen(tts_cfg)
    elif engine != "silero_lab":
        _load_and_warmup_mlx(tts_cfg, engine)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
