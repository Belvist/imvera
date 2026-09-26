"""IMVERA media bridge — FreeSWITCH PCM WebSocket (P0-A uplink / CallActor duplex)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import threading
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

_bridge_start_mono = time.monotonic()

_teardown_executor: concurrent.futures.ThreadPoolExecutor | None = None
_teardown_lock = threading.Lock()
GATE_ROOT = ROOT / ".run" / "freeswitch-gate"
INVITE_META = GATE_ROOT / "synthetic_invite.json"

MODE = os.environ.get("IMVERA_MEDIA_BRIDGE_MODE", "uplink_only").strip().lower()
_sessions: dict[str, FreeSwitchBridgeSession] = {}


def _bridge_mode() -> str:
    if MODE in {"callactor", "voice", "duplex"}:
        return "callactor"
    return "uplink_only"


app = FastAPI(title="IMVERA Media Bridge", version="0.3.0")


@app.on_event("startup")
async def startup() -> None:
    from packages.dialogue_engine.runtime import log_runtime_truth

    log_runtime_truth(log)
    if _bridge_mode() == "callactor":
        # NLP models must be hot before any call: lazy singletons used to
        # load mid-call on turn 1 (measured 6.2 s hole). Synchronous here =
        # loop thread = MPS-safe. Either hot or honestly refusing (readiness
        # 503 + WS 1013 while cold).
        from packages.dialogue_engine.semantic_nlp.warmup import warmup_all

        report = warmup_all()
        for m in report.models:
            log.info(
                "nlp.warm name=%s ok=%s latency_ms=%.1f device=%s err=%s",
                m.name,
                m.ok,
                m.latency_ms,
                m.device,
                m.error,
            )
    asyncio.get_running_loop().create_task(_startup_recovery())


async def _startup_recovery() -> None:
    """P0 plan 4: best-effort recovery shortly after start (non-blocking).

    1. Replay the durable persist spool (PG may have been down).
    2. Sweep orphaned FS audio-stream channels with no live session.
    3. Arm the periodic spool watcher.
    """
    await asyncio.sleep(10)
    await _replay_spool_once("startup")
    await _sweep_orphan_channels()
    asyncio.get_running_loop().create_task(_spool_watcher())


async def _replay_spool_once(reason: str) -> None:
    import os as _os

    spool_dir = _os.environ.get("IMVERA_PERSIST_SPOOL_DIR")
    if not spool_dir:
        return
    try:
        from packages.core import create_call_record_store
        from packages.core.spill import replay_spool

        store = create_call_record_store()
        delegate = getattr(store, "_delegate", store)
        counts = await asyncio.to_thread(replay_spool, spool_dir, delegate)
        if counts["applied"] or counts["stopped"] or counts["quarantined"]:
            log.info("bridge.spool_replay reason=%s %s", reason, counts)
    except Exception:
        log.exception("bridge.spool_replay_failed reason=%s", reason)


async def _spool_watcher() -> None:
    while True:
        await asyncio.sleep(60)
        await _replay_spool_once("watcher")


async def _sweep_orphan_channels() -> None:
    """Hang up parked audio-stream channels with no live bridge session.

    After a bridge restart, FS may still park channels whose WS died.
    Only audio_stream-app channels are touched; grace 60s for fresh setups.
    """
    import time as _time

    started_ago = _time.time() - _bridge_start_mono
    if started_ago < 60:
        await asyncio.sleep(60 - started_ago)
    try:
        from packages.telephony.freeswitch_esl import freeswitch_api
        from services.imvera_media_bridge.callactor import _live_actors

        out = await freeswitch_api("show channels as json", timeout_s=5.0)
    except Exception:
        log.exception("bridge.sweep.esl_unavailable")
        return
    try:
        import json as _json

        data = _json.loads(out)
        rows = data.get("rows", data if isinstance(data, list) else [])
    except Exception:
        log.warning("bridge.sweep.unparseable")
        return
    live_uuids = set(_live_actors)
    for row in rows if isinstance(rows, list) else []:
        uuid = str(row.get("uuid", ""))
        app = str(row.get("application", "") or row.get("app", ""))
        if not uuid or "audio_stream" not in app:
            continue
        if uuid in live_uuids:
            continue
        try:
            from packages.telephony.freeswitch_esl import hangup_channel

            await hangup_channel(uuid)
            log.info("bridge.sweep.orphan_hangup fs_uuid=%s", uuid)
        except Exception:
            log.exception("bridge.sweep.hangup_failed fs_uuid=%s", uuid)


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
    try:
        from packages.voice_runtime.trace import trace_stats

        payload["trace"] = trace_stats()
    except Exception:
        pass
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
        from packages.dialogue_engine.runtime import runtime_truth
        from packages.dialogue_engine.semantic_nlp.warmup import warmth

        report = warmth()
        payload.update(
            {
                "stt": stt,
                "tts": tts,
                "llm": llm,
                "dialogue": runtime_truth(),
                "nlp": (
                    {
                        "all_hot": report.all_hot,
                        "models": [
                            {
                                "name": m.name,
                                "ok": m.ok,
                                "latency_ms": round(m.latency_ms, 1),
                                "device": m.device,
                            }
                            for m in report.models
                        ],
                    }
                    if report is not None
                    else {"all_hot": False, "models": []}
                ),
            }
        )
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
        _teardown_in_background(session)
        log.info("bridge.session.closed call_id=%s", call_id)


def _teardown_in_background(session: FreeSwitchBridgeSession) -> None:
    """Session WAV artifacts off teardown (P0 plan 3c, diagnostic only)."""
    global _teardown_executor
    with _teardown_lock:
        if _teardown_executor is None:
            _teardown_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="teardown-uplink"
            )
        executor = _teardown_executor

    def _run() -> None:
        try:
            _write_session_artifacts(session)
        except Exception:
            log.exception(
                "bridge.teardown.artifacts_failed call_id=%s", session.call_id
            )

    executor.submit(_run)


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
            max(
                abs(int.from_bytes(chunk[j : j + 2], "little", signed=True))
                for j in range(0, len(chunk) - 1, 2)
            ),
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
    from packages.dialogue_engine.runtime import log_runtime_truth

    log_runtime_truth(log)
    port = int(os.environ.get("IMVERA_MEDIA_BRIDGE_PORT", "9210"))
    mode = _bridge_mode()
    log.info("media_bridge.start mode=%s port=%s", mode, port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
