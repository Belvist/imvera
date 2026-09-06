"""Voice API routes — WebSocket media + health."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from packages.contracts.runtime import RuntimeEvent
from packages.core import create_call_record_store
from packages.dialogue.session import CallSession
from packages.voice_runtime.audio import AudioEnvelope
from packages.voice_runtime.runtime import VoiceRuntime, VoiceRuntimeConfig
from services.stt.http_provider import HttpSTTProvider
from services.tts.http_provider import HttpTTSProvider

router = APIRouter()
_store = create_call_record_store()
_runtimes: dict[str, VoiceRuntime] = {}


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
    stt_url = os.environ.get("IMVERA_STT_URL")
    tts_url = os.environ.get("IMVERA_TTS_URL")
    if not stt_url or not tts_url:
        await websocket.close(code=1013, reason="STT/TTS endpoints not configured")
        return

    await websocket.accept()
    session = CallSession(call_id=call_id, family_id=family_id, store=_store)

    async def send_audio(chunk: AudioEnvelope) -> None:
        await websocket.send_bytes(chunk.pcm_s16le)

    async def emit(event: RuntimeEvent) -> None:
        await websocket.send_text(
            json.dumps(
                {"type": event.event_type.value, "payload": event.payload},
                ensure_ascii=False,
            )
        )

    runtime = VoiceRuntime(
        call_id=call_id,
        family_id=family_id,
        session=session,
        stt=HttpSTTProvider(stt_url),
        tts=HttpTTSProvider(tts_url),
        send_audio=send_audio,
        emit=emit,
        config=VoiceRuntimeConfig(
            playback_buffer_ms=int(os.environ.get("IMVERA_PLAYBACK_BUFFER_MS", "200")),
        ),
    )
    _runtimes[call_id] = runtime
    try:
        await runtime.start_call()
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if "bytes" in message and message["bytes"]:
                rate = int(websocket.query_params.get("sample_rate", "16000"))
                await runtime.on_pcm(message["bytes"], rate)
            elif "text" in message and message["text"]:
                data = json.loads(message["text"])
                if data.get("type") == "media.ready":
                    await runtime.handle_media_ready(int(data.get("sample_rate", 16000)))
                elif data.get("type") == "stop":
                    await runtime.stop()
                    break
    except WebSocketDisconnect:
        await runtime.stop()
    finally:
        _runtimes.pop(call_id, None)


def new_call_id() -> str:
    return f"call-{uuid.uuid4().hex[:12]}"
