"""IMVERA voice-service — versioned public API over CallActor."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from packages.contracts.runtime import RuntimeEvent, RuntimeEventType
from packages.core import create_call_record_store
from packages.core.pg_store import PostgresCallRecordStore
from packages.voice_runtime.call_actor import MediaCallbacks, build_call_actor
from packages.voice_runtime.call_registry import CallBinding, build_call_registry
from services.providers.http_clients import close_shared_async_client, get_shared_async_client
from packages.voice_runtime.trace import record_event

_store = create_call_record_store()
_call_registry = build_call_registry(_store)


def _telephony_shared_store_ready() -> tuple[bool, str]:
    """Telephony must not silently use process-local InMemory CallBinding."""
    if not os.environ.get("IMVERA_PG_URL"):
        return (
            False,
            "IMVERA_PG_URL unset; telephony transport requires shared Postgres CallBinding store",
        )
    if not isinstance(_store, PostgresCallRecordStore):
        return (
            False,
            "telephony transport requires PostgresCallRecordStore, not process-local memory",
        )
    return True, ""


@dataclass
class VoiceCallSession:
    call_id: str
    family_id: str
    person_id: str
    profile_id: str
    transport: str
    actor: Any
    events: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    event_seq: int = 0
    stopped: bool = False
    audio_out: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=64))
    media_connected: bool = False


_sessions: dict[str, VoiceCallSession] = {}
_max_sessions = int(os.environ.get("IMVERA_VOICE_MAX_SESSIONS", "4"))
_audio_queue_max = int(os.environ.get("IMVERA_VOICE_AUDIO_QUEUE_MAX", "64"))


async def _enqueue_audio(session: VoiceCallSession, pcm: bytes) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 5.0
    while True:
        try:
            session.audio_out.put_nowait(pcm)
            return
        except asyncio.QueueFull:
            if loop.time() >= deadline:
                raise RuntimeError("voice media downlink backpressure timeout")
            await asyncio.sleep(0.01)


async def _audio_writer(session: VoiceCallSession, websocket: WebSocket) -> None:
    while not session.stopped:
        try:
            pcm = await asyncio.wait_for(session.audio_out.get(), timeout=0.5)
        except TimeoutError:
            continue
        await websocket.send_bytes(pcm)


class CreateCallRequest(BaseModel):
    person_id: str = Field(min_length=1)
    profile_id: str = Field(default="m5")
    transport: str = Field(default="browser")
    family_id: str = Field(default="fam-voice")
    elder_name: str = Field(default="")
    mission: dict[str, Any] | None = None


def _parse_mission(raw: dict[str, Any] | None):
    if not raw:
        return None
    from packages.dialogue_engine.mission import CallMission

    return CallMission.model_validate(raw)


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _urls() -> tuple[str, str, str]:
    stt = os.environ.get("IMVERA_STT_URL", "http://127.0.0.1:9101")
    tts = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    llm = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    return stt, tts, llm


async def _enqueue_event(session: VoiceCallSession, event: RuntimeEvent) -> None:
    session.event_seq += 1
    row = {
        "id": session.event_seq,
        "type": event.event_type.value,
        "payload": event.payload,
    }
    record_event(session.call_id, event)
    await session.events.put(row)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_shared_async_client()
    yield
    await close_shared_async_client()


app = FastAPI(title="IMVERA Voice Service", version="0.1.0", lifespan=lifespan)


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "live", "service": "voice-service"}


@app.get("/health/ready")
def health_ready() -> dict[str, Any]:
    blockers: list[str] = []
    if len(_sessions) >= _max_sessions:
        blockers.append("session capacity reached")
    return {
        "status": "ready" if not blockers else "blocked",
        "active_sessions": len(_sessions),
        "blockers": blockers,
    }


@app.get("/version")
def version() -> dict[str, str]:
    return {"git_sha": _git_sha(), "service": "voice-service", "api": "v1"}


@app.post("/v1/calls")
async def create_call(body: CreateCallRequest) -> dict[str, Any]:
    if len(_sessions) >= _max_sessions:
        raise HTTPException(503, detail="voice session capacity reached")
    call_id = f"call-{uuid.uuid4().hex[:12]}"
    mission_obj = _parse_mission(body.mission)
    mission_id = ""
    if mission_obj is not None:
        mission_id = mission_obj.mission_id
    elif isinstance(body.mission, dict):
        mission_id = str(body.mission.get("mission_id") or "")

    transport = body.transport.strip().lower()
    if transport in {"freeswitch", "sip", "telephony"}:
        ready, reason = _telephony_shared_store_ready()
        if not ready:
            raise HTTPException(status_code=503, detail=reason)

    # Durable binding in shared CallRecordStore (PG in prod) — survives process boundary.
    _call_registry.register(
        CallBinding(
            call_id=call_id,
            family_id=body.family_id,
            person_id=body.person_id,
            elder_name=body.elder_name,
            transport=body.transport,
            mission=body.mission,
            mission_id=mission_id,
        )
    )
    _store.ensure_call(call_id, body.family_id)

    if transport in {"freeswitch", "sip", "telephony"}:
        # Single conversation owner: media-bridge CallActor. Do not start a second brain here.
        from packages.telephony.product_originate import originate_product_call

        originate = await originate_product_call(call_id=call_id)
        fs_uuid = originate.get("fs_uuid")
        if isinstance(fs_uuid, str) and fs_uuid:
            _call_registry.bind_fs_uuid(call_id, fs_uuid)
        return {
            "call_id": call_id,
            "transport": body.transport,
            "mission_id": mission_id,
            "telephony": originate,
            "status": "registered" if originate.get("ok") else "registered_telephony_pending",
            "owner": "media_bridge_callactor",
        }

    stt_url, tts_url, llm_url = _urls()
    session_holder: VoiceCallSession | None = None

    async def emit(event: RuntimeEvent) -> None:
        assert session_holder is not None
        await _enqueue_event(session_holder, event)

    async def send_pcm(pcm: bytes) -> None:
        await _enqueue_audio(session_holder, pcm)
        await emit(
            RuntimeEvent(call_id, RuntimeEventType.TTS_CHUNK_READY, {"bytes": len(pcm)})
        )

    async def flush() -> None:
        await emit(RuntimeEvent(call_id, RuntimeEventType.PLAYBACK_PROGRESS, {"flush": True}))

    async def hangup() -> None:
        if session_holder:
            session_holder.stopped = True

    actor = build_call_actor(
        call_id=call_id,
        family_id=body.family_id,
        elder_name=body.elder_name,
        stt_url=stt_url,
        tts_url=tts_url,
        llm_url=llm_url,
        media=MediaCallbacks(send_pcm=send_pcm, flush=flush, hangup=hangup, emit=emit),
        store=_store,
        mission=mission_obj,
    )
    session_holder = VoiceCallSession(
        call_id=call_id,
        family_id=body.family_id,
        person_id=body.person_id,
        profile_id=body.profile_id,
        transport=body.transport,
        actor=actor,
    )
    _sessions[call_id] = session_holder
    actor.start()
    return {
        "call_id": call_id,
        "transport": body.transport,
        "mission_id": mission_id,
        "telephony": None,
        "owner": "voice_service_callactor",
    }


@app.get("/v1/calls/{call_id}")
def get_call_status(call_id: str) -> dict[str, Any]:
    session = _sessions.get(call_id)
    if session is None:
        raise HTTPException(404, detail="call not found")
    state = session.actor.session.state
    return {
        "call_id": call_id,
        "person_id": session.person_id,
        "transport": session.transport,
        "fsm_state": state.fsm_state.value,
        "stopped": session.stopped,
        "events_emitted": session.event_seq,
    }


@app.post("/v1/calls/{call_id}/stop")
async def stop_call(call_id: str) -> dict[str, str]:
    session = _sessions.get(call_id)
    if session is None:
        return {"status": "not_found"}
    if not session.stopped:
        session.stopped = True
        await session.actor.stop()
        _sessions.pop(call_id, None)
    return {"status": "stopped"}


@app.get("/v1/calls/{call_id}/events")
async def stream_events(call_id: str, after: int = 0) -> StreamingResponse:
    session = _sessions.get(call_id)
    if session is None:
        raise HTTPException(404, detail="call not found")

    async def event_stream():
        cursor = after
        while not session.stopped or cursor < session.event_seq:
            while cursor < session.event_seq:
                cursor += 1
                # events are 1-indexed in session.event_seq counter
                pass
            try:
                item = await asyncio.wait_for(session.events.get(), timeout=1.0)
                if item["id"] <= after:
                    continue
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            except TimeoutError:
                if session.stopped:
                    break
                yield ": keepalive\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/v1/calls/{call_id}/result")
def call_result(
    call_id: str,
    family_id: str | None = None,
) -> dict[str, Any]:
    """Resolve family via query, shared CallBinding store, or live session — never wrong default."""
    resolved = family_id
    if not resolved:
        session = _sessions.get(call_id)
        if session is not None:
            resolved = session.family_id
    if not resolved:
        resolved = _call_registry.family_id_for(call_id)
    if not resolved:
        raise HTTPException(
            404,
            detail="family_id required: pass ?family_id=... or create call via POST /v1/calls",
        )
    result = _store.get_call_result(call_id, resolved)
    if result is None:
        raise HTTPException(404, detail="result not available")
    return result.model_dump(mode="json")


@app.websocket("/v1/calls/{call_id}/media")
async def media_ws(websocket: WebSocket, call_id: str) -> None:
    session = _sessions.get(call_id)
    if session is None:
        await websocket.close(code=4404)
        return
    if session.media_connected:
        await websocket.close(code=4409, reason="media already connected")
        return
    await websocket.accept()
    session.media_connected = True
    writer_task = asyncio.create_task(_audio_writer(session, websocket))
    output_rate = int(websocket.query_params.get("sample_rate", "16000"))
    frame_bytes = output_rate * 2 * 20 // 1000
    await session.actor.on_media_ready(
        output_rate,
        frame_bytes,
        input_sample_rate=output_rate,
    )
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if "bytes" in message and message["bytes"]:
                rate = int(websocket.query_params.get("sample_rate", str(output_rate)))
                await session.actor.push_pcm(message["bytes"], rate)
            elif "text" in message and message["text"]:
                data = json.loads(message["text"])
                if data.get("type") == "stop":
                    break
    except WebSocketDisconnect:
        pass
    finally:
        session.media_connected = False
        try:
            while True:
                pcm = session.audio_out.get_nowait()
                await websocket.send_bytes(pcm)
        except asyncio.QueueEmpty:
            pass
        writer_task.cancel()
        await asyncio.gather(writer_task, return_exceptions=True)
        await stop_call(call_id)


def main() -> None:
    port = int(os.environ.get("IMVERA_VOICE_SERVICE_PORT", "9300"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
