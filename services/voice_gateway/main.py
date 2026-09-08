"""Voice gateway — Asterisk chan_websocket media + CallActor per call."""

from __future__ import annotations

import asyncio
import audioop
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import uvicorn
import websockets
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from packages.contracts.runtime import RuntimeEvent, RuntimeEventType
from packages.telephony.ws_protocol import (
    flush_media_command,
    is_media_start,
    parse_control_message,
    parse_media_start,
)
from packages.voice_runtime.agent_debug_log import agent_debug_log
from packages.telephony.livekit_webhook import verify_and_parse_webhook
from services.voice_gateway.livekit_supervisor import get_livekit_supervisor

if os.environ.get("IMVERA_ENABLE_EXPERIMENTAL_TELNYX", "0") == "1":
    from services.voice_gateway.telnyx_media import handle_telnyx_media_websocket

from packages.voice_runtime.audio_audit import apply_audio_audit_env, audio_audit_enabled
from packages.voice_runtime.audio_channels import extract_client_uplink
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks, build_call_actor
from packages.voice_runtime.trace import record_event

log = logging.getLogger("voice_gateway")

ASTERISK_APP_HTTP = os.environ.get("IMVERA_ASTERISK_APP_HTTP", "http://127.0.0.1:9201")
ASTERISK_HTTP = os.environ.get("IMVERA_ASTERISK_HTTP", "http://127.0.0.1:8088")
WS_DIAG = os.environ.get("IMVERA_WS_DIAG", "0") == "1"
WS_DIAG_DIR = Path(__file__).resolve().parents[2] / ".run" / "ws-diag"
INJECT_PACE = os.environ.get("IMVERA_INJECT_PACE", "1") == "1"
CAPTURE_DIAG = os.environ.get("IMVERA_CAPTURE_DIAG", "0") == "1"
CAPTURE_DUMP = os.environ.get("IMVERA_CAPTURE_DUMP", "")
TTS_WARMUP_BUDGET_S = float(os.environ.get("IMVERA_TTS_FIRST_PCM_BUDGET_S", "8.0"))


def _log_ws_control(call_id: str, role: str, raw: str, parsed: dict | None) -> None:
    if not WS_DIAG:
        return
    WS_DIAG_DIR.mkdir(parents=True, exist_ok=True)
    path = WS_DIAG_DIR / f"{call_id}.jsonl"
    row = {
        "role": role,
        "raw": raw[:500],
        "parsed_event": (parsed or {}).get("event"),
        "format": (parsed or {}).get("format"),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _urls() -> tuple[str, str, str]:
    stt = os.environ.get("IMVERA_STT_URL", "http://127.0.0.1:9101")
    tts = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    llm = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    return stt, tts, llm


async def _warm_tts_pipeline() -> None:
    """Prime MLX TTS so first live call is not 10–30s silent."""
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
            "TTS warmup slow: first_pcm in %.1fs (budget %.1fs)",
            first_s,
            TTS_WARMUP_BUDGET_S,
        )
    else:
        log.info("TTS warmup OK: first_pcm in %.2fs", first_s)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    if os.environ.get("IMVERA_GATEWAY_TTS_WARMUP", "0") == "1":
        try:
            await asyncio.wait_for(_warm_tts_pipeline(), timeout=30.0)
        except asyncio.TimeoutError:
            log.error(
                "TTS warmup timed out at gateway startup (30s) — run make voice-call-gate"
            )
    yield


app = FastAPI(title="IMVERA Voice Gateway", version="0.2.0", lifespan=_lifespan)

get_livekit_supervisor().set_gateway_urls(_urls)


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
    capture_channels: int = 1
    ptime_ms: int = 20
    capture_bytes: int = 0
    capture_rms_peak: float = 0.0
    _capture_dump: object | None = None
    inject_bytes_sent: int = 0
    _inject_first_logged: bool = False
    _capture_task: asyncio.Task | None = None
    _inject_buf: bytearray = field(default_factory=bytearray)
    _capture_summary_emitted: bool = False
    _debug_capture_ticks: int = 0


_sessions: dict[str, CallSession] = {}


def _record_capture_summary(session: CallSession) -> None:
    """Emit gateway capture stats once per call (Zoiper hangup uses WS disconnect)."""
    if session._capture_summary_emitted:
        return
    session._capture_summary_emitted = True
    print(
        f"call {session.call_id} capture_bytes={session.capture_bytes} "
        f"capture_rms_peak={session.capture_rms_peak:.1f} "
        f"inject_bytes_sent={session.inject_bytes_sent}",
        flush=True,
    )
    log.info(
        "call %s capture_bytes=%s capture_rms_peak=%.1f inject_bytes_sent=%s",
        session.call_id,
        session.capture_bytes,
        session.capture_rms_peak,
        session.inject_bytes_sent,
    )
    record_event(
        session.call_id,
        RuntimeEvent(
            session.call_id,
            RuntimeEventType.STAGE_TIMING,
            {
                "stage": "capture.summary",
                "capture_bytes": session.capture_bytes,
                "capture_rms_peak": round(session.capture_rms_peak, 1),
                "inject_bytes_sent": session.inject_bytes_sent,
                "capture_ws_frames": session._debug_capture_ticks,
            },
        ),
    )


class OpenCallRequest(BaseModel):
    family_id: str = Field(default="fam-voice")
    elder_name: str = Field(default="")
    sip_channel_id: str = ""


class AttachCaptureRequest(BaseModel):
    connection_id: str


class RtpStatsRequest(BaseModel):
    rxcount: int = 0
    txcount: int = 0
    rxjitter: float = 0.0
    rx_packet_loss: float = 0.0


def _pcm_frame_bytes(session: CallSession) -> int:
    if session.inject_encoding in ("ulaw", "alaw"):
        return session.inject_sample_rate * 2 * session.ptime_ms // 1000
    return session.inject_frame_size


def _pcm_rms(pcm: bytes) -> float:
    if len(pcm) < 2:
        return 0.0
    import array
    import math

    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return 0.0
    acc = sum(s * s for s in samples)
    return math.sqrt(acc / len(samples))


async def _send_inject_payload(
    session: CallSession, call_id: str, payload: bytes
) -> None:
    if session.inject_ws is None:
        return
    await session.inject_ws.send_bytes(payload)
    session.inject_bytes_sent += len(payload)
    if INJECT_PACE and session.ptime_ms > 0:
        await asyncio.sleep(session.ptime_ms / 1000.0)
    if not session._inject_first_logged:
        session._inject_first_logged = True
        log.info(
            "inject first frame call_id=%s bytes=%s enc=%s",
            call_id,
            len(payload),
            session.inject_encoding,
        )


async def _inference_blockers() -> list[str]:
    stt, tts, llm = _urls()
    blockers: list[str] = []
    async with httpx.AsyncClient(timeout=2.0) as client:
        for name, base in (("stt", stt), ("tts", tts), ("llm", llm)):
            try:
                response = await client.get(f"{base.rstrip('/')}/health/ready")
                if response.status_code != 200:
                    detail = response.text[:200]
                    blockers.append(f"{name}: HTTP {response.status_code} {detail}")
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
    return {"status": "ok", "stt": stt, "tts": tts, "llm": llm}


@app.get("/internal/calls/active")
async def list_active_calls() -> dict:
    return {"calls": list(_sessions.keys())}


@app.post("/internal/calls/{call_id}/rtp_stats")
async def ingest_rtp_stats(call_id: str, body: RtpStatsRequest) -> dict:
    session = _sessions.get(call_id)
    if not session:
        raise HTTPException(404, detail="call not found")
    session.actor.note_rtp_statistics(
        rxcount=body.rxcount,
        txcount=body.txcount,
        rxjitter=body.rxjitter,
        rx_packet_loss=body.rx_packet_loss,
    )
    return {"status": "ok"}


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
    blockers = await _inference_blockers()
    if blockers:
        log.error("refusing call %s — inference not ready: %s", call_id, blockers)
        raise HTTPException(503, detail={"error": "inference not ready", "blockers": blockers})
    if call_id in _sessions:
        raise HTTPException(409, detail="call already open")
    for stale_id in list(_sessions.keys()):
        log.warning("evicting stale gateway session %s for new call %s", stale_id, call_id)
        await close_call(stale_id)
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
            await _send_inject_payload(session, call_id, payload)

    async def _emit_tail_pcm(*, discard: bool) -> None:
        if not session._inject_buf:
            return
        chunk = bytes(session._inject_buf)
        session._inject_buf.clear()
        if discard:
            return
        if len(chunk) % 2:
            chunk += b"\x00"
        if session.inject_encoding in ("ulaw", "alaw"):
            if session.inject_encoding == "ulaw":
                payload = audioop.lin2ulaw(chunk, 2)
            else:
                payload = audioop.lin2alaw(chunk, 2)
        else:
            payload = chunk
        await _send_inject_payload(session, call_id, payload)

    async def prime_downlink() -> None:
        if session.inject_ws is None:
            return
        if session.inject_encoding == "ulaw":
            payload = bytes([0xFF] * session.inject_frame_size)
        elif session.inject_encoding == "alaw":
            payload = bytes([0xD5] * session.inject_frame_size)
        else:
            payload = bytes(session.inject_frame_size)
        for _ in range(3):
            await _send_inject_payload(session, call_id, payload)

    async def finish_downlink() -> None:
        if session.inject_ws is None:
            return
        await _emit_tail_pcm(discard=False)
        log.info(
            "inject finish call_id=%s bytes_sent=%s",
            call_id,
            session.inject_bytes_sent,
        )

    async def abort_downlink() -> None:
        if session.inject_ws is None:
            return
        session._inject_buf.clear()
        await session.inject_ws.send_text(flush_media_command())
        log.info(
            "inject abort call_id=%s bytes_sent=%s",
            call_id,
            session.inject_bytes_sent,
        )

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
        MediaCallbacks(
            send_pcm=send_pcm,
            flush=abort_downlink,
            finish=finish_downlink,
            hangup=hangup,
            emit=emit,
            prime_downlink=prime_downlink,
        ),
    )
    session.actor = actor
    _sessions[call_id] = session
    if CAPTURE_DUMP:
        dump_path = Path(CAPTURE_DUMP).expanduser()
        if "{call_id}" in str(dump_path):
            dump_path = Path(str(dump_path).format(call_id=call_id))
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        session._capture_dump = dump_path.open("wb")
    actor.start()
    return {"status": "opened", "call_id": call_id}


@app.post("/internal/calls/{call_id}/close")
async def close_call(call_id: str) -> dict:
    session = _sessions.pop(call_id, None)
    if session:
        _record_capture_summary(session)
        if session._capture_task and not session._capture_task.done():
            session._capture_task.cancel()
        if session._capture_dump is not None:
            session._capture_dump.close()
            session._capture_dump = None
        await session.actor.stop()
    return {"status": "closed", "capture_bytes": session.capture_bytes if session else 0}


async def _maybe_media_ready(session: CallSession) -> None:
    if session.capture_ready and session.inject_ready and not session.media_ready.is_set():
        session.media_ready.set()
        log.info(
            "media_ready call_id=%s capture_sr=%s inject_sr=%s inject_enc=%s",
            session.call_id,
            session.capture_sample_rate,
            session.inject_sample_rate,
            session.inject_encoding,
        )
        await session.actor.on_media_ready(
            session.inject_sample_rate,
            session.inject_frame_size,
            input_sample_rate=session.capture_sample_rate,
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
                    pcm = extract_client_uplink(message, channels=session.capture_channels)
                    await session.actor.push_pcm(pcm, session.capture_sample_rate)
                    continue
                text = message.decode("utf-8", errors="replace") if isinstance(message, bytes) else str(message)
                data = parse_control_message(text)
                _log_ws_control(session.call_id, "incoming_capture", text, data)
                if not data:
                    continue
                if is_media_start(data):
                    fmt = parse_media_start(data)
                    session.capture_sample_rate = fmt.sample_rate
                    session.capture_frame_size = fmt.frame_size_bytes
                    session.capture_channels = fmt.channels
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
                data = parse_control_message(raw)
                _log_ws_control(session.call_id, role, raw, data)
                if not data:
                    continue
                if is_media_start(data):
                    fmt = parse_media_start(data)
                    session.ptime_ms = fmt.ptime_ms
                    if role == "capture":
                        session.capture_sample_rate = fmt.sample_rate
                        session.capture_frame_size = fmt.frame_size_bytes
                        session.capture_channels = fmt.channels
                        session.capture_ready = True
                    else:
                        session.inject_sample_rate = fmt.sample_rate
                        session.inject_frame_size = fmt.frame_size_bytes
                        session.inject_encoding = fmt.encoding
                        session.inject_ready = True
                    await _maybe_media_ready(session)
            elif "bytes" in message and message["bytes"] and role == "capture":
                raw_pcm = message["bytes"]
                session.capture_bytes += len(raw_pcm)
                pcm = extract_client_uplink(raw_pcm, channels=session.capture_channels)
                if session._capture_dump is not None:
                    session._capture_dump.write(raw_pcm)
                rms = _pcm_rms(pcm)
                session.actor.note_capture_ingress(len(pcm), rms)
                if rms > session.capture_rms_peak:
                    session.capture_rms_peak = rms
                session._debug_capture_ticks += 1
                tick = session._debug_capture_ticks
                if audio_audit_enabled() and (
                    tick in {1, 50, 200, 500} or tick % 500 == 0
                ):
                    record_event(
                        session.call_id,
                        RuntimeEvent(
                            session.call_id,
                            RuntimeEventType.STAGE_TIMING,
                            {
                                "stage": "capture.tick",
                                "tick": tick,
                                "capture_bytes": session.capture_bytes,
                                "rms": round(rms, 1),
                                "capture_rms_peak": round(session.capture_rms_peak, 1),
                            },
                        ),
                    )
                if tick in {1, 50, 200, 500}:
                    # region agent log
                    agent_debug_log(
                        "A",
                        "voice_gateway.py:capture",
                        "capture_tick",
                        {
                            "call_id": session.call_id,
                            "tick": session._debug_capture_ticks,
                            "capture_bytes": session.capture_bytes,
                            "rms": round(rms, 1),
                            "capture_rms_peak": round(session.capture_rms_peak, 1),
                        },
                    )
                    # endregion
                await session.actor.push_pcm(pcm, session.capture_sample_rate)
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
            _record_capture_summary(session)
            await session.actor.stop()
            _sessions.pop(session.call_id, None)


def _session_for_leg(role: str) -> CallSession | None:
    """Bind Asterisk WS legs to the newest session still missing that leg."""
    candidates = list(_sessions.values())
    for session in reversed(candidates):
        if role == "capture" and session.capture_ws is None:
            return session
        if role == "inject" and session.inject_ws is None:
            return session
    if len(candidates) == 1:
        return candidates[0]
    return None


@app.websocket("/asterisk/capture")
async def asterisk_capture(websocket: WebSocket) -> None:
    session = _session_for_leg("capture")
    if session is None:
        await websocket.close(code=1013)
        return
    await _attach_leg(session, "capture", websocket)


@app.websocket("/asterisk/inject")
async def asterisk_inject(websocket: WebSocket) -> None:
    session = _session_for_leg("inject")
    if session is None:
        await websocket.close(code=1013)
        return
    await _attach_leg(session, "inject", websocket)


@app.post("/livekit/webhook")
async def livekit_webhook(request: Request) -> dict:
    """Signed LiveKit webhooks — SIP participant → LiveKitCallSession (ADR-012)."""
    body = await request.body()
    auth = request.headers.get("Authorization", "")
    api_key = os.environ.get("LIVEKIT_API_KEY", "devkey")
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "secret")
    try:
        event = verify_and_parse_webhook(body, auth, api_key, api_secret)
    except Exception as exc:
        log.warning("LiveKit webhook rejected: %s", exc)
        raise HTTPException(401, detail="invalid webhook signature") from exc
    return await get_livekit_supervisor().handle_webhook(event)


if os.environ.get("IMVERA_ENABLE_EXPERIMENTAL_TELNYX", "0") == "1":

    @app.websocket("/telnyx/media")
    async def telnyx_media(websocket: WebSocket) -> None:
        """EXPERIMENTAL Telnyx path (ADR-011 rejected). Disabled by default."""
        await handle_telnyx_media_websocket(websocket)


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
