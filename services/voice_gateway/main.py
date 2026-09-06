"""Voice gateway — Asterisk chan_websocket media + CallActor per call."""

from __future__ import annotations

import asyncio
import audioop
import json
import logging
import os
from dataclasses import dataclass, field

import httpx
import uvicorn
import websockets
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from packages.contracts.runtime import RuntimeEvent
from packages.telephony.ws_protocol import (
    flush_media_command,
    is_control_message,
    is_media_start,
    parse_media_start,
)
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks, build_call_actor
from packages.voice_runtime.trace import record_event

app = FastAPI(title="IMVERA Voice Gateway", version="0.2.0")
log = logging.getLogger("voice_gateway")

ASTERISK_APP_HTTP = os.environ.get("IMVERA_ASTERISK_APP_HTTP", "http://127.0.0.1:9201")
ASTERISK_HTTP = os.environ.get("IMVERA_ASTERISK_HTTP", "http://127.0.0.1:8088")


def _urls() -> tuple[str, str, str]:
    stt = os.environ.get("IMVERA_STT_URL", "http://127.0.0.1:9101")
    tts = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    llm = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    return stt, tts, llm


@dataclass
class CallSession:
    call_id: str
    family_id: str
    elder_name: str
    actor: CallActor
    capture_ws: WebSocket | None = None
    inject_ws: WebSocket | None = None
    capture_ready: bool = False
    inject_ready: bool = False
    media_ready: asyncio.Event = field(default_factory=asyncio.Event)
    inject_sample_rate: int = 16000
    inject_frame_size: int = 640
    inject_encoding: str = "slin16"
    capture_sample_rate: int = 16000
    capture_frame_size: int = 640
    ptime_ms: int = 20
    capture_bytes: int = 0
    inject_bytes_sent: int = 0
    _capture_task: asyncio.Task | None = None
    _inject_buf: bytearray = field(default_factory=bytearray)


_sessions: dict[str, CallSession] = {}


class OpenCallRequest(BaseModel):
    family_id: str = Field(default="fam-voice")
    elder_name: str = Field(default="")
    sip_channel_id: str = ""


class AttachCaptureRequest(BaseModel):
    connection_id: str


def _pcm_frame_bytes(session: CallSession) -> int:
    if session.inject_encoding in ("ulaw", "alaw"):
        return session.inject_sample_rate * 2 * session.ptime_ms // 1000
    return session.inject_frame_size


@app.get("/health/ready")
async def ready() -> dict:
    stt, tts, llm = _urls()
    return {"status": "ok", "stt": stt, "tts": tts, "llm": llm}


@app.get("/internal/calls/active")
async def list_active_calls() -> dict:
    return {"calls": list(_sessions.keys())}


@app.get("/internal/calls/{call_id}/status")
async def call_status(call_id: str) -> dict:
    session = _sessions.get(call_id)
    if not session:
        raise HTTPException(404, detail="call not found")
    return {
        "call_id": call_id,
        "capture_bytes": session.capture_bytes,
        "capture_ready": session.capture_ready,
        "inject_ready": session.inject_ready,
        "inject_bytes_sent": session.inject_bytes_sent,
    }


@app.get("/internal/calls/{call_id}/trace")
async def call_trace(call_id: str) -> dict:
    from packages.voice_runtime.trace import trace_path

    path = trace_path(call_id)
    if not path.exists():
        raise HTTPException(404, detail="trace not found")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return {"call_id": call_id, "events": [json.loads(line) for line in lines if line]}


@app.post("/internal/calls/{call_id}/open")
async def open_call(call_id: str, body: OpenCallRequest) -> dict:
    if call_id in _sessions:
        raise HTTPException(409, detail="call already open")
    stt, tts, llm = _urls()
    elder = body.elder_name or os.environ.get("IMVERA_ELDER_DISPLAY_NAME", "собеседником")
    session = CallSession(call_id=call_id, family_id=body.family_id, elder_name=elder, actor=None)  # type: ignore[arg-type]

    async def send_pcm(pcm: bytes) -> None:
        if session.inject_ws is None:
            return
        session._inject_buf.extend(pcm)
        frame = _pcm_frame_bytes(session)
        while len(session._inject_buf) >= frame:
            chunk = bytes(session._inject_buf[:frame])
            del session._inject_buf[:frame]
            if session.inject_encoding in ("ulaw", "alaw"):
                if session.inject_encoding == "ulaw":
                    payload = audioop.lin2ulaw(chunk, 2)
                else:
                    payload = audioop.lin2alaw(chunk, 2)
            else:
                payload = chunk
            await session.inject_ws.send_bytes(payload)
            session.inject_bytes_sent += len(payload)

    async def flush() -> None:
        if session.inject_ws is None:
            return
        await session.inject_ws.send_text(flush_media_command())

    async def hangup() -> None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(f"{ASTERISK_APP_HTTP}/internal/calls/{call_id}/hangup")
        except httpx.HTTPError:
            pass

    async def emit(event: RuntimeEvent) -> None:
        record_event(call_id, event)

    actor = build_call_actor(
        call_id,
        body.family_id,
        elder,
        stt,
        tts,
        llm,
        MediaCallbacks(send_pcm=send_pcm, flush=flush, hangup=hangup, emit=emit),
    )
    session.actor = actor
    _sessions[call_id] = session
    actor.start()
    return {"status": "opened", "call_id": call_id}


@app.post("/internal/calls/{call_id}/close")
async def close_call(call_id: str) -> dict:
    session = _sessions.pop(call_id, None)
    if session:
        log.info("call %s capture_bytes=%s", call_id, session.capture_bytes)
        if session._capture_task and not session._capture_task.done():
            session._capture_task.cancel()
        await session.actor.stop()
    return {"status": "closed", "capture_bytes": session.capture_bytes if session else 0}


async def _maybe_media_ready(session: CallSession) -> None:
    if session.capture_ready and session.inject_ready and not session.media_ready.is_set():
        session.media_ready.set()
        await session.actor.on_media_ready(
            session.inject_sample_rate, session.inject_frame_size
        )


async def _run_incoming_capture(session: CallSession, connection_id: str) -> None:
    ws_url = f"{ASTERISK_HTTP.replace('http://', 'ws://')}/media/{connection_id}"
    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        async with websockets.connect(ws_url, open_timeout=10) as ws:
            while True:
                message = await ws.recv()
                if isinstance(message, bytes):
                    session.capture_bytes += len(message)
                    await session.actor.push_pcm(message, session.capture_sample_rate)
                    continue
                if not is_control_message(message):
                    continue
                data = json.loads(message)
                if is_media_start(data):
                    fmt = parse_media_start(data)
                    session.capture_sample_rate = fmt.sample_rate
                    session.capture_frame_size = fmt.frame_size_bytes
                    session.ptime_ms = fmt.ptime_ms
                    session.capture_ready = True
                    await _maybe_media_ready(session)
    except Exception as exc:
        log.warning("incoming capture ended for %s: %s", session.call_id, exc)
    finally:
        session.capture_ready = False
        if (
            session.media_ready.is_set()
            and session.capture_bytes == 0
            and loop.time() - started > 1.0
        ):
            await session.actor.on_capture_lost()


@app.post("/internal/calls/{call_id}/attach_incoming_capture")
async def attach_incoming_capture(call_id: str, body: AttachCaptureRequest) -> dict:
    session = _sessions.get(call_id)
    if not session:
        raise HTTPException(404, detail="call not open")
    if session._capture_task and not session._capture_task.done():
        return {"status": "already_attached"}
    session._capture_task = asyncio.create_task(
        _run_incoming_capture(session, body.connection_id)
    )
    return {"status": "attaching", "connection_id": body.connection_id}


async def _attach_leg(session: CallSession, role: str, websocket: WebSocket) -> None:
    await websocket.accept()
    if role == "capture":
        session.capture_ws = websocket
    else:
        session.inject_ws = websocket

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if "text" in message and message["text"]:
                raw = message["text"]
                if not is_control_message(raw):
                    continue
                data = json.loads(raw)
                if is_media_start(data):
                    fmt = parse_media_start(data)
                    session.inject_sample_rate = fmt.sample_rate
                    session.inject_frame_size = fmt.frame_size_bytes
                    session.inject_encoding = fmt.encoding
                    session.ptime_ms = fmt.ptime_ms
                    if role == "capture":
                        session.capture_sample_rate = fmt.sample_rate
                        session.capture_frame_size = fmt.frame_size_bytes
                        session.capture_ready = True
                    else:
                        session.inject_ready = True
                    await _maybe_media_ready(session)
            elif "bytes" in message and message["bytes"] and role == "capture":
                session.capture_bytes += len(message["bytes"])
                await session.actor.push_pcm(
                    message["bytes"], session.capture_sample_rate
                )
    except WebSocketDisconnect:
        pass
    finally:
        if role == "capture":
            session.capture_ws = None
            session.capture_ready = False
        else:
            session.inject_ws = None
            session.inject_ready = False
        if not session.capture_ready and not session.inject_ready:
            await session.actor.stop()
            _sessions.pop(session.call_id, None)


@app.websocket("/asterisk/capture")
async def asterisk_capture(websocket: WebSocket) -> None:
    if len(_sessions) != 1:
        await websocket.close(code=1013)
        return
    session = next(iter(_sessions.values()))
    await _attach_leg(session, "capture", websocket)


@app.websocket("/asterisk/inject")
async def asterisk_inject(websocket: WebSocket) -> None:
    if len(_sessions) != 1:
        await websocket.close(code=1013)
        return
    session = next(iter(_sessions.values()))
    await _attach_leg(session, "inject", websocket)


@app.websocket("/media/{call_id}")
async def browser_media(
    websocket: WebSocket,
    call_id: str,
    family_id: str = "fam-voice",
    elder_name: str = "",
) -> None:
    """Browser/lab WebSocket — bidirectional PCM without Asterisk."""
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
                {"type": event.event_type.value, "payload": event.payload},
                ensure_ascii=False,
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
