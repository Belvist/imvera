"""IMVERA media bridge — FreeSWITCH uplink PCM WebSocket (P0-A: READ only)."""

from __future__ import annotations

import logging
import os
import time
import wave
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from packages.telephony.freeswitch_bridge import TARGET_SAMPLE_RATE, FreeSwitchBridgeSession
from packages.voice_runtime.audio import pcm_rms_s16le
from tools.telephony_gate.evidence import MediaGateEvidence, write_evidence

log = logging.getLogger("imvera_media_bridge")
GATE_ROOT = Path(".run/freeswitch-gate")
INVITE_META = GATE_ROOT / "synthetic_invite.json"


app = FastAPI(title="IMVERA Media Bridge", version="0.2.0")
_sessions: dict[str, FreeSwitchBridgeSession] = {}


async def _noop_inbound(_frame) -> None:
    return


@app.get("/health/ready")
async def ready() -> dict:
    return {
        "status": "ok",
        "active_sessions": len(_sessions),
        "mode": "uplink_only",
        "gate": "p0a",
    }


@app.websocket("/stream/{fs_uuid}")
async def fs_pcm_stream(websocket: WebSocket, fs_uuid: str) -> None:
    """P0-A: receive caller PCM only. Outbound 880 Hz is FreeSWITCH tone_stream."""
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

    downlink = invite.get("synthetic_downlink_path", str(GATE_ROOT / "synthetic_downlink.u8"))
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
        raw_inbound_wav=str(wav_path) if raw else "",
        synthetic_downlink_wav=downlink,
        gate_phase="p0a",
    )
    write_evidence(artifact_dir / "media_gate_evidence.json", evidence)


def main() -> None:
    port = int(os.environ.get("IMVERA_MEDIA_BRIDGE_PORT", "9210"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
