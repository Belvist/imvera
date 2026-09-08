"""IMVERA perception service — capture, echo gate, turn boundary (Docker-runnable)."""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from packages.voice_perception.config import PerceptionConfig, perception_config_from_env
from packages.voice_perception.session import PerceptionSession

log = logging.getLogger("imvera_perception")
app = FastAPI(title="IMVERA Perception", version="0.1.0")

_sessions: dict[str, PerceptionSession] = {}


class SessionCreate(BaseModel):
    call_id: str
    sample_rate: int = 16000
    echo_ref_gate: bool | None = None
    lab_half_duplex: bool | None = None
    lab_barge_in: bool | None = None


class DownlinkFrame(BaseModel):
    call_id: str
    pcm_b64: str = Field(default="")


class TextEchoCheck(BaseModel):
    call_id: str
    user_text: str
    bot_text: str
    allowlist: list[str] = Field(default_factory=list)


def _session_config(body: SessionCreate) -> PerceptionConfig:
    base = perception_config_from_env(sample_rate=body.sample_rate)
    return PerceptionConfig(
        sample_rate=body.sample_rate,
        echo_ref_gate=body.echo_ref_gate if body.echo_ref_gate is not None else base.echo_ref_gate,
        lab_half_duplex=body.lab_half_duplex if body.lab_half_duplex is not None else base.lab_half_duplex,
        lab_barge_in=body.lab_barge_in if body.lab_barge_in is not None else base.lab_barge_in,
        post_speech_pause_ms=base.post_speech_pause_ms,
        uplink_preroll_ms=base.uplink_preroll_ms,
    )


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok", "service": "imvera_perception"}


@app.get("/health/ready")
async def health_ready() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "imvera_perception",
        "active_sessions": len(_sessions),
    }


@app.post("/v1/sessions")
async def create_session(body: SessionCreate) -> dict[str, object]:
    _sessions[body.call_id] = PerceptionSession(_session_config(body))
    return {"call_id": body.call_id, "status": "created"}


@app.delete("/v1/sessions/{call_id}")
async def delete_session(call_id: str) -> dict[str, str]:
    _sessions.pop(call_id, None)
    return {"call_id": call_id, "status": "deleted"}


@app.post("/v1/downlink")
async def push_downlink(body: DownlinkFrame) -> dict[str, str]:
    session = _sessions.get(body.call_id)
    if session is None:
        return {"status": "missing_session"}
    pcm = base64.b64decode(body.pcm_b64) if body.pcm_b64 else b""
    session.push_downlink(pcm)
    return {"status": "ok"}


@app.post("/v1/text_echo")
async def check_text_echo(body: TextEchoCheck) -> dict[str, object]:
    session = _sessions.get(body.call_id)
    if session is None:
        session = PerceptionSession(perception_config_from_env())
        _sessions[body.call_id] = session
    is_echo = session.is_assistant_text_echo(
        body.user_text,
        [body.bot_text],
        allowlist=frozenset(body.allowlist),
    )
    return {"is_echo": is_echo}


@app.websocket("/v1/stream/{call_id}")
async def perception_stream(websocket: WebSocket, call_id: str) -> None:
    """Per-call uplink stream: binary PCM in, JSON decisions out.

    Control messages (JSON text):
      {"type":"config","sample_rate":16000}
      {"type":"playback_started","intent":"opening_wellness"}
      {"type":"playback_completed","now_mono":123.4}
      {"type":"listen_enabled"}
      {"type":"downlink","pcm_b64":"..."}

    Binary frames: uplink PCM s16le mono at configured sample_rate.
    """
    await websocket.accept()
    config = perception_config_from_env()
    session = PerceptionSession(config)
    _sessions[call_id] = session
    log.info("perception.ws.connected call_id=%s", call_id)
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if "bytes" in message and message["bytes"]:
                pcm = message["bytes"]
                payload = _process_uplink_frame(session, pcm, playback_active=False)
                await websocket.send_json(payload)
                continue
            text = message.get("text")
            if not text:
                continue
            data = json.loads(text)
            reply = await _handle_control(session, data)
            if reply is not None:
                await websocket.send_json(reply)
    except WebSocketDisconnect:
        pass
    finally:
        _sessions.pop(call_id, None)
        log.info("perception.ws.closed call_id=%s", call_id)


def _process_uplink_frame(
    session: PerceptionSession,
    pcm: bytes,
    *,
    playback_active: bool,
    now_mono: float = 0.0,
) -> dict[str, Any]:
    decision = session.process_uplink(
        pcm,
        playback_active=playback_active,
        now_mono=now_mono,
    )
    return {
        "type": "uplink_decision",
        "feed_vad": decision.feed_vad,
        "append_preroll": decision.append_preroll,
        "blocked": decision.blocked,
        "buffer_only": decision.buffer_only,
        "echo_verdict": str(decision.echo_verdict) if decision.echo_verdict else None,
        "echo_score": decision.echo_score,
        "turn_phase": str(session.turn_manager.phase),
    }


async def _handle_control(session: PerceptionSession, data: dict[str, Any]) -> dict[str, Any] | None:
    msg_type = str(data.get("type", ""))
    if msg_type == "config":
        sample_rate = int(data.get("sample_rate", 16000))
        session.config = PerceptionConfig(
            sample_rate=sample_rate,
            echo_ref_gate=bool(data.get("echo_ref_gate", session.config.echo_ref_gate)),
            lab_half_duplex=bool(data.get("lab_half_duplex", session.config.lab_half_duplex)),
            lab_barge_in=bool(data.get("lab_barge_in", session.config.lab_barge_in)),
            post_speech_pause_ms=int(data.get("post_speech_pause_ms", session.config.post_speech_pause_ms)),
            uplink_preroll_ms=int(data.get("uplink_preroll_ms", session.config.uplink_preroll_ms)),
        )
        return {"type": "config_ack", "sample_rate": sample_rate}
    if msg_type == "playback_started":
        session.on_playback_started(str(data.get("intent", "")))
        return {"type": "playback_started_ack", "phase": str(session.turn_manager.phase)}
    if msg_type == "playback_completed":
        now_mono = float(data.get("now_mono", 0.0))
        session.on_playback_completed(now_mono)
        return {"type": "playback_completed_ack", "phase": str(session.turn_manager.phase)}
    if msg_type == "listen_enabled":
        preroll_bytes = session.on_listen_enabled()
        return {"type": "listen_enabled_ack", "preroll_bytes": preroll_bytes}
    if msg_type == "downlink":
        pcm = base64.b64decode(str(data.get("pcm_b64", "")))
        session.push_downlink(pcm)
        return {"type": "downlink_ack", "bytes": len(pcm)}
    if msg_type == "uplink":
        pcm = base64.b64decode(str(data.get("pcm_b64", "")))
        playback_active = bool(data.get("playback_active", False))
        now_mono = float(data.get("now_mono", 0.0))
        return _process_uplink_frame(
            session, pcm, playback_active=playback_active, now_mono=now_mono
        )
    return {"type": "error", "message": f"unknown type: {msg_type}"}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("IMVERA_PERCEPTION_PORT", "9110"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
