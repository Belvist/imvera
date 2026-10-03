"""FreeSWITCH WebSocket session with CallActor (Zoiper lab / P0-B preview)."""

from __future__ import annotations

import concurrent.futures
import logging
import os
import subprocess
import sys
import threading
import wave
from pathlib import Path
from typing import Any

import httpx
from fastapi import WebSocket

from packages.contracts.runtime import RuntimeEvent, RuntimeEventType
from packages.core import create_call_record_store
from packages.telephony.adapter import InboundMediaFrame
from packages.telephony.freeswitch_bridge import (
    FRAME_MS,
    FreeSwitchBridgeSession,
    FreeSwitchOutboundMode,
)
from packages.telephony.freeswitch_esl import hangup_channel
from packages.voice_runtime.audio import pcm_rms_s16le
from packages.voice_runtime.call_actor import MediaCallbacks, build_call_actor
from packages.voice_runtime.call_registry import build_call_registry
from packages.voice_runtime.codec_output import bridge_audio_rates, resampler_chain_summary
from packages.voice_runtime.trace import record_event
from services.inference.config import production_mode

log = logging.getLogger("imvera_media_bridge.callactor")
ROOT = Path(__file__).resolve().parents[2]

# P0 plan 4a: live actors by fs_uuid. A second WS for the same channel is
# rejected (two actors would split audio/state) — reconnect needs a new
# channel or an explicit resume window (not yet implemented).
_live_actors: dict[str, str] = {}

_teardown_executor: concurrent.futures.ThreadPoolExecutor | None = None
_teardown_lock = threading.Lock()


def _production_call_limit() -> int | None:
    if not production_mode():
        return None
    from packages.voice_runtime.profile import load_profile

    limit = load_profile().get("limits", {}).get("max_active_calls")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("production profile requires positive integer max_active_calls")
    return limit


class ProductBindingMissing(RuntimeError):
    """Product ?call_id= present but shared CallBinding not found — fail closed."""

    def __init__(self, call_id: str, fs_uuid: str) -> None:
        self.call_id = call_id
        self.fs_uuid = fs_uuid
        super().__init__(f"CallBinding not found for call_id={call_id} fs_uuid={fs_uuid}")


def _gateway_urls() -> tuple[str, str, str]:
    stt = os.environ.get("IMVERA_STT_URL", "http://127.0.0.1:9101")
    tts = os.environ.get("IMVERA_TTS_URL", "http://127.0.0.1:9102")
    llm = os.environ.get("IMVERA_LLM_URL", "http://127.0.0.1:9103")
    return stt, tts, llm


def _resolve_product_mission(websocket: WebSocket, fs_uuid: str):
    """Prefer shared CallBinding (POST /v1/calls → PG) over manual ?mission= JSON.

    Product path (``?call_id=``): fail closed if binding missing — never invent
    daily_check / IMVERA_DEV_FAMILY / mission=None. Lab-only ``?mission=`` JSON
    remains when no product call_id is supplied.
    """
    from packages.dialogue_engine.mission import CallMission

    product_call_id = websocket.query_params.get("call_id") or websocket.query_params.get(
        "imvera_call_id"
    )
    if production_mode() and not product_call_id:
        raise ProductBindingMissing("", fs_uuid)
    if product_call_id:
        # Same store as voice_service: the product path must resolve its binding.
        registry = build_call_registry(create_call_record_store())
        binding = registry.resolve(call_id=product_call_id, fs_uuid=fs_uuid)
        if binding is None:
            raise ProductBindingMissing(product_call_id, fs_uuid)
        registry.bind_fs_uuid(binding.call_id, fs_uuid)
        mission_obj = None
        if binding.mission:
            mission_obj = CallMission.model_validate(binding.mission)
        elder = binding.elder_name or os.environ.get("IMVERA_ELDER_DISPLAY_NAME", "Даниил")
        return binding.call_id, binding.family_id, elder, mission_obj

    # Lab-only fallback: explicit ?mission= JSON (not the product handoff path).
    mission_raw = websocket.query_params.get("mission")
    if mission_raw:
        import json as _json

        mission_obj = CallMission.model_validate(_json.loads(mission_raw))
        call_id = f"fs-{fs_uuid[:8]}"
        family_id = os.environ.get("IMVERA_DEV_FAMILY_ID", "fam-voice")
        elder = os.environ.get("IMVERA_ELDER_DISPLAY_NAME", "Даниил")
        return call_id, family_id, elder, mission_obj

    call_id = f"fs-{fs_uuid[:8]}"
    elder = os.environ.get("IMVERA_ELDER_DISPLAY_NAME", "Даниил")
    family_id = os.environ.get("IMVERA_DEV_FAMILY_ID", "fam-voice")
    return call_id, family_id, elder, None


async def inference_blockers() -> list[str]:
    """Product CallActor readiness: STT + TTS required; LLM is not required.

    Comma-separated replica lists are checked one by one; one sick
    replica is a warning, all sick is a blocker.
    """
    from packages.dialogue_engine.semantic_nlp.warmup import nlp_blockers
    from services.providers.replica_pool import split_urls

    stt, tts, _llm = _gateway_urls()
    blockers: list[str] = nlp_blockers()
    try:
        _production_call_limit()
    except ValueError as exc:
        blockers.append(str(exc))
    async with httpx.AsyncClient(timeout=2.0) as client:
        for name, base in (("stt", stt), ("tts", tts)):
            urls = split_urls(base)
            sick = 0
            for url in urls:
                try:
                    response = await client.get(f"{url}/health/ready")
                    if response.status_code != 200:
                        sick += 1
                except httpx.HTTPError:
                    sick += 1
            if sick >= len(urls):
                blockers.append(f"{name}: all {len(urls)} replicas sick")
            elif sick:
                log.warning("%s: %d/%d replicas sick", name, sick, len(urls))
    return blockers


async def handle_callactor_ws(websocket: WebSocket, fs_uuid: str) -> None:
    """Bidirectional FS stream: uplink → CallActor, TTS → mod_audio_stream JSON playback."""
    blockers = await inference_blockers()
    if blockers:
        await websocket.close(code=1013, reason=f"inference not ready: {', '.join(blockers)}")
        log.error("callactor.ws.rejected fs_uuid=%s blockers=%s", fs_uuid, blockers)
        return

    if fs_uuid in _live_actors:
        log.error("callactor.duplicate_rejected fs_uuid=%s live_call_id=%s",
                  fs_uuid, _live_actors[fs_uuid])
        await websocket.close(code=1008, reason="duplicate channel session")
        return
    limit = _production_call_limit()
    if limit is not None and len(_live_actors) >= limit:
        await websocket.close(code=1013, reason="bridge call capacity reached")
        return

    # No await between checking capacity and reserving on this process's
    # event loop. Setup counts too; every failure releases the same slot.
    _live_actors[fs_uuid] = fs_uuid
    try:
        try:
            call_id, family_id, elder, mission_obj = _resolve_product_mission(websocket, fs_uuid)
        except ProductBindingMissing as exc:
            log.error(
                "callactor.binding.missing call_id=%s fs_uuid=%s — rejecting WS, no CallActor",
                exc.call_id,
                exc.fs_uuid,
            )
            await websocket.close(code=1008, reason="product CallBinding not found")
            return
        _live_actors[fs_uuid] = call_id
        await _serve_callactor_ws(websocket, fs_uuid, call_id, family_id, elder, mission_obj)
    finally:
        _live_actors.pop(fs_uuid, None)


async def _serve_callactor_ws(
    websocket: WebSocket, fs_uuid: str, call_id: str, family_id: str, elder: str, mission_obj
) -> None:

    stt, tts, llm = _gateway_urls()
    capture_sr, playback_sr = bridge_audio_rates()
    output_frame_bytes = playback_sr * FRAME_MS // 1000 * 2
    chain = resampler_chain_summary(
        bridge_output_rate=playback_sr,
        negotiated_codec=os.environ.get("IMVERA_NEGOTIATED_CODEC", "G722"),
    )

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
        capture_sample_rate=capture_sr,
        playback_sample_rate=playback_sr,
    )
    bridge_holder["bridge"] = bridge

    async def send_pcm(pcm: bytes) -> None:
        await bridge.enqueue_outbound_pcm(pcm)

    async def send_frame(frame: Any) -> None:
        await bridge.enqueue_outbound_pcm(
            frame.pcm_s16le,
            generation_id=frame.generation_id,
            phrase_id=frame.phrase_id,
            sequence=frame.sequence,
        )

    async def cancel_generation(generation_id: str) -> dict[str, Any]:
        return bridge.cancel_generation(generation_id)

    async def request_downstream_stop() -> dict[str, Any]:
        return await bridge.request_downstream_stop()

    async def flush() -> None:
        # Legacy global flush: no longer used on the generation path
        # (see cancel_generation). Kept for MediaCallbacks compatibility.
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
            if stage in {
                "tts.first_pcm",
                "stt.final",
                "llm.render",
                "interpret.fast_path",
                "dialogue.engine_decision",
                "dialogue.planner_decision",
            }:
                log.info("callactor.stage call_id=%s %s", call_id, event.payload)

    actor = build_call_actor(
        call_id,
        family_id,
        elder,
        stt,
        tts,
        llm,
        MediaCallbacks(
            send_pcm=send_pcm,
            flush=flush,
            hangup=hangup,
            emit=emit,
            send_frame=send_frame,
            cancel_generation=cancel_generation,
            request_downstream_stop=request_downstream_stop,
        ),
        mission=mission_obj,
        store=create_call_record_store(),
    )
    actor_holder["actor"] = actor

    try:
        await websocket.accept()
        mission_id = mission_obj.mission_id if mission_obj is not None else ""
        log.info(
            "callactor.ws.connected call_id=%s fs_uuid=%s mission_id=%s "
            "capture_sr=%s playback_sr=%s "
            "negotiated_codec=%s resampler_hops=%s stt=%s tts=%s llm=%s",
            call_id, fs_uuid, mission_id or "-", capture_sr, playback_sr,
            chain["negotiated_codec"], chain["resampler_hops"], stt, tts, llm,
        )
        actor.start()
        await actor.on_media_ready(
            playback_sr,
            output_frame_bytes,
            input_sample_rate=capture_sr,
        )
        await bridge.handle_ws(websocket)
    finally:
        await actor.stop()
        _teardown_in_background(call_id, bridge, fs_uuid)
        log.info("callactor.session.closed call_id=%s", call_id)


def _teardown_in_background(
    call_id: str, bridge: FreeSwitchBridgeSession, fs_uuid: str
) -> None:
    """WAV dump + forensic collect off the teardown hot path (P0 plan 3c).

    Diagnostic artifacts only — spool owns durability. Fire-and-forget on
    a single serial worker; failures are logged, never raised.
    """
    global _teardown_executor
    with _teardown_lock:
        if _teardown_executor is None:
            _teardown_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="teardown"
            )

    def _run() -> None:
        try:
            _persist_ws_uplink(call_id, bridge)
        except Exception:
            log.exception("callactor.teardown.wav_failed call_id=%s", call_id)
        try:
            _run_forensic_collect(fs_uuid, call_id)
        except Exception:
            log.exception("callactor.teardown.forensic_failed call_id=%s", call_id)
        try:
            from packages.voice_runtime.trace import flush_traces, write_call_summary

            if flush_traces(timeout_s=5.0):
                write_call_summary(call_id)
        except Exception:
            log.exception("callactor.teardown.summary_failed call_id=%s", call_id)

    _teardown_executor.submit(_run)


def _persist_ws_uplink(call_id: str, bridge: FreeSwitchBridgeSession) -> None:
    raw = bridge.raw_inbound_pcm()
    if not raw:
        return
    out_dir = ROOT / ".run" / "freeswitch-forensic" / call_id
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / "ws_raw_inbound.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(bridge.capture_sample_rate)
        wf.writeframes(raw)


def _run_forensic_collect(fs_uuid: str, call_id: str) -> None:
    script = ROOT / "scripts" / "freeswitch_forensic_collect.py"
    if not script.is_file():
        return
    try:
        result = subprocess.run(
            [sys.executable, str(script), fs_uuid, "--call-id", call_id],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30.0,
        )
        if result.stdout:
            log.info("callactor.forensic\n%s", result.stdout.strip())
        if result.returncode not in (0, 2):
            log.warning(
                "callactor.forensic.failed code=%s stderr=%s",
                result.returncode,
                result.stderr.strip(),
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("callactor.forensic.error: %s", exc)
