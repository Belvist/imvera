"""TTS MLX worker — NDJSON streaming on port 9102."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import queue
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
    WorkerState,
    check_deadline,
    mount_health,
    new_request_id,
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


def _produce_chunks(req: SynthesizeRequest, out_q: queue.Queue) -> None:
    cfg = _load_config()
    tts_cfg = cfg["models"]["tts"]
    voice = req.voice or tts_cfg["voice"]
    lang = req.language or tts_cfg["lang_code"]
    seq = 0
    try:
        for result in _tts.generate(
            text=req.text,
            voice=voice,
            lang_code=lang,
            stream=True,
            streaming_interval=tts_cfg.get("streaming_interval", 0.32),
        ):
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


@app.on_event("startup")
def warmup() -> None:
    global _tts
    cfg = _load_config()
    model_id = cfg["models"]["tts"]["id"]
    try:
        from mlx_audio.tts.utils import load_model

        _tts = load_model(model_id)
        state.model_revision = model_id
        state.ready = True
    except Exception as exc:
        state.warmup_error = str(exc)
        state.ready = False


mount_health(app, state, "tts")


async def _ndjson_stream(req: SynthesizeRequest) -> AsyncIterator[bytes]:
    check_deadline(req.deadline)
    out_q: queue.Queue = queue.Queue(maxsize=8)

    def produce() -> None:
        _produce_chunks(req, out_q)

    fut = executor.submit(produce)
    got_audio = False
    try:
        while True:
            item = await asyncio.to_thread(out_q.get)
            if item is None:
                break
            if req.generation_id in _cancelled:
                yield (json.dumps({"done": True, "cancelled": True}) + "\n").encode()
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
    if not state.ready or _tts is None:
        raise HTTPException(503, detail=state.warmup_error or "not ready")
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
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
