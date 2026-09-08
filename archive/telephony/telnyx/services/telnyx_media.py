"""Telnyx /telnyx/media WebSocket — EXPERIMENTAL, rejected per ADR-012.

Not for production. See packages/telephony/EXPERIMENTAL.md.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from packages.contracts.runtime import RuntimeEvent, RuntimeEventType
from packages.telephony.telnyx_adapter import (
    TelnyxMediaSession,
    TelnyxStreamKeys,
    new_telnyx_call_id,
    parse_stream_keys,
)
from packages.telephony.telnyx_codec import (
    TARGET_SAMPLE_RATE,
    TelnyxCodecError,
    TelnyxNegotiatedFormat,
)
from packages.telephony.telnyx_ws import TelnyxWsRouter
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks, build_call_actor
from packages.voice_runtime.trace import record_event

log = logging.getLogger(__name__)


@dataclass
class TelnyxCallSession:
    call_id: str
    keys: TelnyxStreamKeys
    actor: CallActor
    adapter: TelnyxMediaSession
    router: TelnyxWsRouter
    _closed: bool = False


_telnyx_sessions: dict[str, TelnyxCallSession] = {}
_telnyx_by_stream: dict[str, str] = {}
_telnyx_by_call_control: dict[str, str] = {}


def _gateway_urls() -> tuple[str, str, str]:
    stt = os.environ.get("IMVERA_STT_URL", "http://127.0.0.1:9101")
    tts = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    llm = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    return stt, tts, llm


async def _close_telnyx_session(call_id: str) -> None:
    session = _telnyx_sessions.pop(call_id, None)
    if session is None:
        return
    _telnyx_by_stream.pop(session.keys.stream_id, None)
    _telnyx_by_call_control.pop(session.keys.call_control_id, None)
    if session._closed:
        return
    session._closed = True
    await session.adapter.handle_stop()
    await session.actor.stop()


async def _emit_stage(call_id: str, stage: str, **payload: Any) -> None:
    record_event(
        call_id,
        RuntimeEvent(
            call_id,
            RuntimeEventType.STAGE_TIMING,
            {"stage": stage, **payload},
        ),
    )


async def _create_session_from_start(
    data: dict[str, Any],
    *,
    send_ws_text,
) -> TelnyxCallSession:
    start = data.get("start") or {}
    stream_id = str(data.get("stream_id", ""))
    keys = parse_stream_keys(start, stream_id)
    media_format = start.get("media_format") or {}
    fmt = TelnyxNegotiatedFormat.from_start(media_format)

    if keys.call_control_id and keys.call_control_id in _telnyx_by_call_control:
        call_id = _telnyx_by_call_control[keys.call_control_id]
    else:
        call_id = new_telnyx_call_id(keys.call_control_id or stream_id)

    async def emit_stage(stage: str, **payload: Any) -> None:
        await _emit_stage(call_id, stage, **payload)

    actor_holder: dict[str, CallActor] = {}

    async def push_pcm(pcm: bytes, sample_rate: int) -> None:
        await actor_holder["actor"].push_pcm(pcm, sample_rate)

    def note_transport(nbytes: int, rms: float) -> None:
        actor_holder["actor"].note_capture_ingress(nbytes, rms)

    adapter = TelnyxMediaSession(
        call_id=call_id,
        keys=keys,
        fmt=fmt,
        push_pcm=push_pcm,
        send_ws_text=send_ws_text,
        emit_stage=emit_stage,
        note_transport=note_transport,
    )

    stt, tts, llm = _gateway_urls()
    elder = os.environ.get("IMVERA_ELDER_DISPLAY_NAME", "собеседником")

    async def send_pcm(pcm: bytes) -> None:
        await adapter.send_outbound_pcm(pcm, TARGET_SAMPLE_RATE)

    async def flush() -> None:
        await adapter.send_clear()

    async def hangup() -> None:
        await _close_telnyx_session(call_id)

    async def emit(event: RuntimeEvent) -> None:
        record_event(call_id, event)

    actor = build_call_actor(
        call_id,
        "fam-voice",
        elder,
        stt,
        tts,
        llm,
        MediaCallbacks(send_pcm=send_pcm, flush=flush, hangup=hangup, emit=emit),
    )
    actor_holder["actor"] = actor
    actor.start()

    router = TelnyxWsRouter(session=adapter)
    session = TelnyxCallSession(
        call_id=call_id,
        keys=keys,
        actor=actor,
        adapter=adapter,
        router=router,
    )
    _telnyx_sessions[call_id] = session
    _telnyx_by_stream[stream_id] = call_id
    if keys.call_control_id:
        _telnyx_by_call_control[keys.call_control_id] = call_id
    return session


async def handle_telnyx_media_websocket(websocket: WebSocket) -> None:
    """Production entry: Telnyx media stream WebSocket lifecycle."""
    await websocket.accept()
    call_id = ""
    session: TelnyxCallSession | None = None

    async def send_ws_text(text: str) -> None:
        await websocket.send_text(text)

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            raw = message.get("text")
            if not raw:
                continue

            data = json.loads(raw)
            event = str(data.get("event", "")).lower()

            if event == "start" and session is None:
                try:
                    session = await _create_session_from_start(
                        data, send_ws_text=send_ws_text
                    )
                    call_id = session.call_id
                except TelnyxCodecError as exc:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "event": "error",
                                "error": {
                                    "code": 415,
                                    "title": "UNSUPPORTED_MEDIA",
                                    "detail": str(exc),
                                },
                            }
                        )
                    )
                    break

            router = session.router if session else TelnyxWsRouter()
            keep_open = await router.handle_text(raw)

            if (
                session is not None
                and event == "start"
                and router._started
                and not session.actor._media_ready  # noqa: SLF001
            ):
                await session.actor.on_media_ready(
                    TARGET_SAMPLE_RATE,
                    640,
                    input_sample_rate=TARGET_SAMPLE_RATE,
                )

            if not keep_open:
                break
    except WebSocketDisconnect:
        pass
    except json.JSONDecodeError:
        log.warning("Telnyx WS invalid JSON")
    finally:
        if call_id:
            await _close_telnyx_session(call_id)


def get_telnyx_session(call_id: str) -> TelnyxCallSession | None:
    return _telnyx_sessions.get(call_id)


def reset_telnyx_sessions_for_tests() -> None:
    _telnyx_sessions.clear()
    _telnyx_by_stream.clear()
    _telnyx_by_call_control.clear()
