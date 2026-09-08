"""IMVERA media bridge — FreeSWITCH PCM WebSocket (transport P0, no AI)."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
import wave
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from packages.telephony.freeswitch_bridge import FRAME_MS, TARGET_SAMPLE_RATE, FreeSwitchBridgeSession
from tools.telephony_gate.evidence import MediaGateEvidence, write_evidence
from tools.telephony_gate.tone import MEDIA_GATE_PROBE_OUTBOUND_HZ, generate_tone_s16le

log = logging.getLogger("imvera_media_bridge")
GATE_ROOT = Path(".run/freeswitch-gate")
PROBE_HZ = float(os.environ.get("IMVERA_FS_PROBE_HZ", str(MEDIA_GATE_PROBE_OUTBOUND_HZ)))

app = FastAPI(title="IMVERA Media Bridge", version="0.1.0")
_sessions: dict[str, FreeSwitchBridgeSession] = {}


def _chunk_pcm(pcm: bytes, frame_bytes: int) -> list[bytes]:
    return [pcm[i : i + frame_bytes] for i in range(0, len(pcm), frame_bytes)]


async def _probe_tone_loop(session: FreeSwitchBridgeSession) -> None:
    """Immediate 880 Hz outbound after WS connect — do not wait for inbound."""
    frame_bytes = TARGET_SAMPLE_RATE * FRAME_MS // 1000 * 2
    phase = 0
    samples_per_chunk = TARGET_SAMPLE_RATE * FRAME_MS // 1000
    try:
        while not session._closed:
            pcm = bytearray()
            for i in range(samples_per_chunk):
                sample = int(
                    8192.0
                    * math.sin(2.0 * math.pi * PROBE_HZ * (phase + i) / TARGET_SAMPLE_RATE)
                )
                pcm.extend(int(sample).to_bytes(2, "little", signed=True))
            phase += samples_per_chunk
            for chunk in _chunk_pcm(bytes(pcm), frame_bytes):
                await session.enqueue_outbound_pcm(chunk)
            await asyncio.sleep(FRAME_MS / 1000.0)
    except asyncio.CancelledError:
        raise


async def _noop_inbound(_frame) -> None:
    return


@app.get("/health/ready")
async def ready() -> dict:
    return {"status": "ok", "active_sessions": len(_sessions)}


@app.websocket("/stream/{fs_uuid}")
async def fs_pcm_stream(websocket: WebSocket, fs_uuid: str) -> None:
    call_id = f"fs-{fs_uuid[:8]}"
    session = FreeSwitchBridgeSession(
        call_id=call_id,
        fs_uuid=fs_uuid,
        on_inbound=_noop_inbound,
    )
    _sessions[call_id] = session
    probe = asyncio.create_task(_probe_tone_loop(session))
    await websocket.accept()
    log.info("bridge.ws.connected call_id=%s fs_uuid=%s", call_id, fs_uuid)
    try:
        await session.handle_ws(websocket)
    except WebSocketDisconnect:
        pass
    finally:
        probe.cancel()
        try:
            await probe
        except asyncio.CancelledError:
            pass
        _sessions.pop(call_id, None)
        _write_session_artifacts(session)
        log.info("bridge.session.closed call_id=%s", call_id)


def _write_session_artifacts(session: FreeSwitchBridgeSession) -> None:
    artifact_dir = GATE_ROOT / session.call_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    raw = session.raw_inbound_pcm()
    if raw:
        wav_path = artifact_dir / "raw_inbound.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(TARGET_SAMPLE_RATE)
            wf.writeframes(raw)
    evidence = MediaGateEvidence(
        call_id=session.call_id,
        bridge_ws_connected_at=session.ws_connected_at,
        first_outbound_pcm_at=session.first_outbound_pcm_at,
        first_inbound_pcm_at=session.first_inbound_pcm_at,
        bridge_rx_frames=session.counters.carrier_rx_frames,
        bridge_rx_bytes=session.counters.carrier_rx_bytes,
        bridge_tx_frames=session.counters.carrier_tx_frames,
        bridge_tx_bytes=session.counters.carrier_tx_bytes,
        raw_inbound_wav=str(artifact_dir / "raw_inbound.wav") if raw else "",
    )
    write_evidence(artifact_dir / "media_gate_evidence.json", evidence)


def main() -> None:
    port = int(os.environ.get("IMVERA_MEDIA_BRIDGE_PORT", "9210"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
