"""Voice API routes — WebSocket media via unified CallActor."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from packages.contracts.runtime import RuntimeEvent
from packages.core import create_call_record_store
from packages.voice_runtime.call_actor import MediaCallbacks, build_call_actor
from packages.voice_runtime.trace import record_event

router = APIRouter()
_store = create_call_record_store()
_actors: dict[str, Any] = {}


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


def _provider_urls() -> tuple[str, str, str]:
    stt = os.environ.get("IMVERA_STT_URL")
    tts = os.environ.get("IMVERA_TTS_URL")
    llm = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    if not stt or not tts:
        raise HTTPException(status_code=503, detail="STT/TTS endpoints not configured")
    return stt, tts, llm


@router.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "live"}


@router.get("/health/ready")
def health_ready() -> dict[str, Any]:
    blockers: list[str] = []
    if not os.environ.get("IMVERA_PG_URL") and not os.environ.get("IMVERA_VOICE_DATABASE_URL"):
        blockers.append("no voice database URL")
    if not os.environ.get("IMVERA_STT_URL"):
        blockers.append("IMVERA_STT_URL unset")
    if not os.environ.get("IMVERA_TTS_URL"):
        blockers.append("IMVERA_TTS_URL unset")
    ready = len(blockers) == 0
    return {"status": "ready" if ready else "blocked", "blockers": blockers}


@router.get("/version")
def version() -> dict[str, str]:
    return {
        "git_sha": _git_sha(),
        "architecture": "ADR-008",
        "schema": "voice-v1",
        "dialogue_path": "CallActor",
    }


@router.get("/calls/{call_id}")
def get_call(call_id: str, family_id: str = Query(..., min_length=1)) -> dict:
    result = _store.get_call_result(call_id, family_id)
    if result is None:
        raise HTTPException(status_code=404, detail="call not found for family")
    return result.model_dump(mode="json")


@router.websocket("/ws/voice/{call_id}")
async def voice_ws(
    websocket: WebSocket,
    call_id: str,
    family_id: str = Query(..., min_length=1),
) -> None:
    try:
        stt_url, tts_url, llm_url = _provider_urls()
    except HTTPException:
        await websocket.close(code=1013, reason="STT/TTS endpoints not configured")
        return

    await websocket.accept()
    output_rate = int(websocket.query_params.get("sample_rate", "16000"))
    frame_bytes = output_rate * 2 * 20 // 1000

    async def send_pcm(pcm: bytes) -> None:
        await websocket.send_bytes(pcm)

    async def flush() -> None:
        await websocket.send_text(json.dumps({"type": "playback.flush"}, ensure_ascii=False))

    async def hangup() -> None:
        await websocket.send_text(json.dumps({"type": "call.ended"}, ensure_ascii=False))

    async def emit(event: RuntimeEvent) -> None:
        record_event(call_id, event)
        await websocket.send_text(
            json.dumps(
                {"type": event.event_type.value, "payload": event.payload},
                ensure_ascii=False,
            )
        )

    actor = build_call_actor(
        call_id=call_id,
        family_id=family_id,
        elder_name=os.environ.get("IMVERA_ELDER_NAME", ""),
        stt_url=stt_url,
        tts_url=tts_url,
        llm_url=llm_url,
        media=MediaCallbacks(send_pcm=send_pcm, flush=flush, hangup=hangup, emit=emit),
        store=_store,
    )
    _actors[call_id] = actor
    actor.start()
    try:
        await actor.on_media_ready(output_rate, frame_bytes, input_sample_rate=output_rate)
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if "bytes" in message and message["bytes"]:
                rate = int(websocket.query_params.get("sample_rate", str(output_rate)))
                await actor.push_pcm(message["bytes"], rate)
            elif "text" in message and message["text"]:
                data = json.loads(message["text"])
                if data.get("type") == "media.ready":
                    rate = int(data.get("sample_rate", output_rate))
                    await actor.on_media_ready(
                        rate,
                        rate * 2 * 20 // 1000,
                        input_sample_rate=rate,
                    )
                elif data.get("type") == "stop":
                    await actor.stop()
                    break
    except WebSocketDisconnect:
        await actor.stop()
    finally:
        _actors.pop(call_id, None)


def new_call_id() -> str:
    return f"call-{uuid.uuid4().hex[:12]}"
