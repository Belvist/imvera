"""IMVERA media bridge — FreeSWITCH PCM WebSocket (P0-A uplink / CallActor duplex)."""

from __future__ import annotations

import logging
import os
import time
import wave
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from packages.telephony.freeswitch_bridge import TARGET_SAMPLE_RATE, FreeSwitchBridgeSession
from tools.telephony_gate.evidence import MediaGateEvidence, write_evidence

log = logging.getLogger("imvera_media_bridge")
ROOT = Path(__file__).resolve().parents[2]
GATE_ROOT = ROOT / ".run" / "freeswitch-gate"
INVITE_META = GATE_ROOT / "synthetic_invite.json"

MODE = os.environ.get("IMVERA_MEDIA_BRIDGE_MODE", "uplink_only").strip().lower()
_sessions: dict[str, FreeSwitchBridgeSession] = {}


def _bridge_mode() -> str:
    if MODE in {"callactor", "voice", "duplex"}:
        return "callactor"
    return "uplink_only"


app = FastAPI(title="IMVERA Media Bridge", version="0.3.0")


async def _noop_inbound(_frame) -> None:
    return


@app.get("/health/ready", response_model=None)
async def ready() -> JSONResponse | dict:
    mode = _bridge_mode()
    payload: dict = {
        "status": "ok",
        "active_sessions": len(_sessions),
        "mode": mode,
        "gate": "p0b" if mode == "callactor" else "p0a",
    }
    if mode == "callactor":
        from services.imvera_media_bridge.callactor import inference_blockers

        blockers = await inference_blockers()
        if blockers:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "mode": mode, "blockers": blockers},
            )
        stt = os.environ.get("IMVERA_STT_URL", "http://127.0.0.1:9101")
        tts = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
        llm = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103")
        payload.update({"stt": stt, "tts": tts, "llm": llm})
    return payload


@app.websocket("/stream/{fs_uuid}")
async def fs_pcm_stream(websocket: WebSocket, fs_uuid: str) -> None:
    if _bridge_mode() == "callactor":
        from services.imvera_media_bridge.callactor import handle_callactor_ws

        await handle_callactor_ws(websocket, fs_uuid)
        return

    call_id = f"fs-{fs_uuid[:8]}"
    session = FreeSwitchBridgeSession(
        call_id=call_id,
        fs_uuid=fs_uuid,
        on_inbound=_noop_inbound,
        uplink_only=True,
    )
    _sessions[call_id] = session
    await websocket.accept()
    log.info("bridge.ws.connected call_id=%s fs_uuid=%s mode=uplink_only", call_id, fs_uuid)
    try:
        await session.handle_ws(websocket)
    except WebSocketDisconnect:
        pass
    finally:
        _sessions.pop(call_id, None)
        _write_session_artifacts(session)
        log.info("bridge.session.closed call_id=%s", call_id)


def _load_invite_meta() -> dict:
    if not INVITE_META.exists():
        return {}
    import json

    try:
        return json.loads(INVITE_META.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_session_artifacts(session: FreeSwitchBridgeSession) -> None:
    artifact_dir = GATE_ROOT / session.call_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    invite = _load_invite_meta()
    raw = session.raw_inbound_pcm()
    wav_path = artifact_dir / "raw_inbound.wav"
    if raw:
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(TARGET_SAMPLE_RATE)
            wf.writeframes(raw)

    peak = 0
    rms_peak = 0.0
    nonzero = 0
    from packages.voice_runtime.audio import pcm_rms_s16le

    for i in range(0, len(raw) - 1, 640):
        chunk = raw[i : i + 640]
        if len(chunk) < 2:
            continue
        rms = pcm_rms_s16le(chunk)
        if rms > 50.0:
            nonzero += 1
        rms_peak = max(rms_peak, rms)
        peak = max(
            peak,
            max(abs(int.from_bytes(chunk[j : j + 2], "little", signed=True)) for j in range(0, len(chunk) - 1, 2)),
        )

    downlink_raw = invite.get("synthetic_downlink_path", str(GATE_ROOT / "synthetic_downlink.u8"))
    downlink_path = Path(downlink_raw)
    if not downlink_path.is_absolute():
        downlink_path = ROOT / downlink_path
    evidence = MediaGateEvidence(
        call_id=session.call_id,
        invite_sent_at=invite.get("invite_sent_at"),
        fs_answered_at=invite.get("sip_answered_at"),
        bridge_ws_connected_at=session.ws_connected_at,
        first_inbound_pcm_at=session.first_inbound_pcm_at,
        synthetic_rtp_tx_packets=int(invite.get("synthetic_rtp_tx_packets", 0)),
        synthetic_rtp_tx_bytes=int(invite.get("synthetic_rtp_tx_bytes", 0)),
        bridge_rx_frames=session.counters.carrier_rx_frames,
        bridge_rx_bytes=session.counters.carrier_rx_bytes,
        nonzero_pcm_frames=nonzero,
        inbound_rms_peak=rms_peak,
        inbound_peak_sample=peak,
        raw_inbound_wav=str(wav_path.relative_to(ROOT)) if raw else "",
        synthetic_downlink_wav=str(downlink_path.relative_to(ROOT)),
        gate_phase="p0a",
    )
    write_evidence(artifact_dir / "media_gate_evidence.json", evidence)


def main() -> None:
    GATE_ROOT.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("IMVERA_MEDIA_BRIDGE_PORT", "9210"))
    mode = _bridge_mode()
    log.info("media_bridge.start mode=%s port=%s", mode, port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
