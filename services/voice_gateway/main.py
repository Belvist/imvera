"""Voice gateway — WebSocket media + CallActor per active call."""

from __future__ import annotations

import json
import os

import uvicorn
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect

from packages.contracts.runtime import RuntimeEvent
from packages.voice_runtime.call_actor import build_call_actor

app = FastAPI(title="IMVERA Voice Gateway", version="0.1.0")
_actors: dict[str, object] = {}


def _urls() -> tuple[str, str, str]:
    stt = os.environ.get("IMVERA_STT_URL", "http://127.0.0.1:9101")
    tts = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    llm = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    return stt, tts, llm


@app.get("/health/ready")
async def ready() -> dict:
    stt, tts, llm = _urls()
    return {"status": "ok", "stt": stt, "tts": tts, "llm": llm}


@app.websocket("/media/{call_id}")
async def media_ws(
    websocket: WebSocket,
    call_id: str,
    family_id: str = Query(default="fam-voice"),
    elder_name: str = Query(default=""),
) -> None:
    stt, tts, llm = _urls()
    await websocket.accept()
    display = elder_name or os.environ.get("IMVERA_ELDER_DISPLAY_NAME", "собеседником")

    async def send_audio(chunk) -> None:
        await websocket.send_bytes(chunk.pcm_s16le)

    async def emit(event: RuntimeEvent) -> None:
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
        send_audio,
        emit,
    )
    _actors[call_id] = actor
    actor.start()
    sample_rate = 16000
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if "bytes" in message and message["bytes"]:
                await actor.push_pcm(message["bytes"], sample_rate)
            elif "text" in message and message["text"]:
                data = json.loads(message["text"])
                if data.get("type") == "media.ready":
                    sample_rate = int(data.get("sample_rate", 16000))
                elif data.get("type") == "stop":
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await actor.stop()
        _actors.pop(call_id, None)


@app.websocket("/ws/voice/{call_id}")
async def browser_ws(
    websocket: WebSocket,
    call_id: str,
    family_id: str = Query(..., min_length=1),
) -> None:
    await media_ws(websocket, call_id, family_id=family_id)


def main() -> None:
    port = int(os.environ.get("IMVERA_VOICE_GATEWAY_PORT", "9200"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
