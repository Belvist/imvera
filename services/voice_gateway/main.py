"""Voice gateway — CallActor wiring (production). Telephony = FreeSWITCH bridge (ADR-013)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from packages.contracts.runtime import RuntimeEvent
from packages.voice_runtime.call_actor import MediaCallbacks, build_call_actor
from packages.voice_runtime.trace import record_event

log = logging.getLogger("voice_gateway")

TTS_WARMUP_BUDGET_S = float(os.environ.get("IMVERA_TTS_FIRST_PCM_BUDGET_S", "8.0"))


def _urls() -> tuple[str, str, str]:
    stt = os.environ.get("IMVERA_STT_URL", "http://127.0.0.1:9101")
    tts = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    llm = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    return stt, tts, llm


async def _warm_tts_pipeline() -> None:
    _, tts_url, _ = _urls()
    started = time.monotonic()
    first_s: float | None = None
    try:
        timeout = httpx.Timeout(5.0, read=90.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{tts_url}/v1/synthesize",
                json={
                    "call_id": "gateway-warmup",
                    "generation_id": "gw-warmup",
                    "phrase_id": "gw-w",
                    "text": "А.",
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if data.get("done"):
                        break
                    if data.get("pcm_b64"):
                        if first_s is None:
                            first_s = time.monotonic() - started
    except httpx.HTTPError as exc:
        log.error("TTS warmup failed at startup: %s", exc)
        return
    if first_s is None:
        log.error("TTS warmup produced no PCM at startup")
        return
    if first_s > TTS_WARMUP_BUDGET_S:
        log.error(
            "TTS warmup slow: first_pcm in %.1fs (budget %.1fs)", first_s, TTS_WARMUP_BUDGET_S
        )
    else:
        log.info("TTS warmup OK: first_pcm in %.2fs", first_s)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    if os.environ.get("IMVERA_GATEWAY_TTS_WARMUP", "0") == "1":
        try:
            await asyncio.wait_for(_warm_tts_pipeline(), timeout=30.0)
        except TimeoutError:
            log.error("TTS warmup timed out at gateway startup (30s)")
    yield


app = FastAPI(title="IMVERA Voice Gateway", version="0.3.0", lifespan=_lifespan)


async def _inference_blockers() -> list[str]:
    stt, tts, llm = _urls()
    blockers: list[str] = []
    async with httpx.AsyncClient(timeout=2.0) as client:
        for name, base in (("stt", stt), ("tts", tts), ("llm", llm)):
            try:
                response = await client.get(f"{base.rstrip('/')}/health/ready")
                if response.status_code != 200:
                    blockers.append(f"{name}: HTTP {response.status_code}")
            except httpx.HTTPError as exc:
                blockers.append(f"{name}: {exc}")
    return blockers


@app.get("/health/ready", response_model=None)
async def ready() -> JSONResponse | dict:
    stt, tts, llm = _urls()
    blockers = await _inference_blockers()
    if blockers:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "blockers": blockers,
                "stt": stt,
                "tts": tts,
                "llm": llm,
            },
        )
    return {"status": "ok", "stt": stt, "tts": tts, "llm": llm, "telephony": "freeswitch"}


@app.websocket("/media/{call_id}")
async def browser_media_lab(
    websocket: WebSocket,
    call_id: str,
    family_id: str = "fam-voice",
    elder_name: str = "",
) -> None:
    """Browser/lab WebSocket — bidirectional PCM without telephony edge."""
    await websocket.accept()
    stt, tts, llm = _urls()
    display = elder_name or os.environ.get("IMVERA_ELDER_DISPLAY_NAME", "собеседником")
    sample_rate = 16000

    async def send_pcm(pcm: bytes) -> None:
        await websocket.send_bytes(pcm)

    async def flush() -> None:
        pass

    async def hangup() -> None:
        await websocket.close()

    async def emit(event: RuntimeEvent) -> None:
        record_event(call_id, event)
        await websocket.send_text(
            json.dumps(
                {"type": event.event_type.value, "payload": event.payload}, ensure_ascii=False
            )
        )

    actor = build_call_actor(
        call_id,
        family_id,
        display,
        stt,
        tts,
        llm,
        MediaCallbacks(send_pcm=send_pcm, flush=flush, hangup=hangup, emit=emit),
    )
    actor.start()
    try:
        await actor.on_media_ready(sample_rate, 640)
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if "bytes" in message and message["bytes"]:
                await actor.push_pcm(message["bytes"], sample_rate)
            elif "text" in message and message["text"]:
                data = json.loads(message["text"])
                if data.get("type") == "stop":
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await actor.stop()


def main() -> None:
    port = int(os.environ.get("IMVERA_VOICE_GATEWAY_PORT", "9200"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
