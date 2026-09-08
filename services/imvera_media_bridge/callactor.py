"""FreeSWITCH WebSocket session with CallActor (Zoiper lab / P0-B preview)."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import WebSocket

from packages.contracts.runtime import RuntimeEvent, RuntimeEventType
from packages.telephony.adapter import InboundMediaFrame
from packages.voice_runtime.audio import pcm_rms_s16le
from packages.telephony.freeswitch_bridge import (
    FRAME_MS,
    TARGET_SAMPLE_RATE,
    FreeSwitchBridgeSession,
    FreeSwitchOutboundMode,
)
from packages.telephony.freeswitch_esl import hangup_channel
from packages.voice_runtime.call_actor import MediaCallbacks, build_call_actor
from packages.voice_runtime.trace import record_event

log = logging.getLogger("imvera_media_bridge.callactor")


def _gateway_urls() -> tuple[str, str, str]:
    stt = os.environ.get("IMVERA_STT_URL", "http://127.0.0.1:9101")
    tts = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    llm = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    return stt, tts, llm


async def inference_blockers() -> list[str]:
    stt, tts, llm = _gateway_urls()
    blockers: list[str] = []
    async with httpx.AsyncClient(timeout=2.0) as client:
        for name, base in (("stt", stt), ("tts", tts), ("llm", llm)):
            try:
                response = await client.get(f"{base.rstrip('/')}/health/ready")
                if response.status_code != 200:
                    blockers.append(f"{name}: HTTP {response.status_code}")
            except httpx.HTTPError as exc:
                blockers.append(f"{name}: {exc}")
    return blockers


async def handle_callactor_ws(websocket: WebSocket, fs_uuid: str) -> None:
    """Bidirectional FS stream: uplink → CallActor, TTS → mod_audio_stream JSON playback."""
    blockers = await inference_blockers()
    if blockers:
        await websocket.close(code=1013, reason=f"inference not ready: {', '.join(blockers)}")
        log.error("callactor.ws.rejected fs_uuid=%s blockers=%s", fs_uuid, blockers)
        return

    call_id = f"fs-{fs_uuid[:8]}"
    stt, tts, llm = _gateway_urls()
    elder = os.environ.get("IMVERA_ELDER_DISPLAY_NAME", "Даниил")
    family_id = os.environ.get("IMVERA_DEV_FAMILY_ID", "fam-voice")
    frame_bytes = TARGET_SAMPLE_RATE * FRAME_MS // 1000 * 2

    actor_holder: dict[str, Any] = {}
    bridge_holder: dict[str, FreeSwitchBridgeSession] = {}
    _nonzero_logged = False

    async def on_inbound(frame: InboundMediaFrame) -> None:
        rms = pcm_rms_s16le(frame.pcm_s16le)
        actor_holder["actor"].note_capture_ingress(len(frame.pcm_s16le), rms)
        nonlocal _nonzero_logged
        if not _nonzero_logged and rms > 50.0:
            _nonzero_logged = True
            log.info(
                "callactor.uplink.live call_id=%s rms=%.1f bytes=%s",
                call_id,
                rms,
                len(frame.pcm_s16le),
            )
        await actor_holder["actor"].push_pcm(frame.pcm_s16le, frame.sample_rate)

    bridge = FreeSwitchBridgeSession(
        call_id=call_id,
        fs_uuid=fs_uuid,
        on_inbound=on_inbound,
        uplink_only=False,
        outbound_mode=FreeSwitchOutboundMode.STREAM_AUDIO_JSON,
        sample_rate=TARGET_SAMPLE_RATE,
    )
    bridge_holder["bridge"] = bridge

    async def send_pcm(pcm: bytes) -> None:
        await bridge.enqueue_outbound_pcm(pcm)

    async def flush() -> None:
        return

    async def hangup() -> None:
        await hangup_channel(fs_uuid)

    async def emit(event: RuntimeEvent) -> None:
        record_event(call_id, event)
        if event.event_type == RuntimeEventType.RENDERER_PHRASE_READY:
            speech = str((event.payload or {}).get("text", ""))
            if speech:
                log.info("callactor.vera.phrase call_id=%s text=%s", call_id, speech[:240])
        elif event.event_type == RuntimeEventType.STT_FINAL:
            text = str((event.payload or {}).get("text", ""))
            if text:
                log.info("callactor.user.stt call_id=%s text=%s", call_id, text[:240])
        elif event.event_type == RuntimeEventType.STAGE_TIMING:
            stage = str((event.payload or {}).get("stage", ""))
            if stage in {"tts.first_pcm", "stt.final", "llm.render"}:
                log.info("callactor.stage call_id=%s %s", call_id, event.payload)

    actor = build_call_actor(
        call_id,
        family_id,
        elder,
        stt,
        tts,
        llm,
        MediaCallbacks(send_pcm=send_pcm, flush=flush, hangup=hangup, emit=emit),
    )
    actor_holder["actor"] = actor

    await websocket.accept()
    log.info(
        "callactor.ws.connected call_id=%s fs_uuid=%s stt=%s tts=%s llm=%s",
        call_id,
        fs_uuid,
        stt,
        tts,
        llm,
    )
    actor.start()
    try:
        await actor.on_media_ready(
            TARGET_SAMPLE_RATE,
            frame_bytes,
            input_sample_rate=TARGET_SAMPLE_RATE,
        )
        await bridge.handle_ws(websocket)
    finally:
        await actor.stop()
        log.info("callactor.session.closed call_id=%s", call_id)
