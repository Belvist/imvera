"""LiveKit session supervisor — webhooks → LiveKitCallSession → CallActor."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packages.contracts.runtime import RuntimeEvent, RuntimeEventType
from packages.telephony.livekit_adapter import build_livekit_session
from packages.telephony.livekit_privacy import new_imvera_call_id, redact_room_name, redact_sip_identity
from packages.telephony.livekit_readiness import LiveKitSessionPhase
from packages.telephony.livekit_session import (
    IMVERA_IDENTITY_PREFIX,
    is_imvera_participant_identity,
    is_sip_participant_kind,
)
from packages.telephony.livekit_webhook import LiveKitWebhookEvent
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks, build_call_actor
from packages.voice_runtime.inference_preflight import inference_blockers
from packages.voice_runtime.trace import record_event

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
GATE_ARTIFACT_ROOT = ROOT / ".run" / "livekit-gate"


def _livekit_env() -> tuple[str, str, str]:
    url = os.environ.get("LIVEKIT_URL", "ws://127.0.0.1:7880")
    key = os.environ.get("LIVEKIT_API_KEY", "devkey")
    secret = os.environ.get("LIVEKIT_API_SECRET", "secret")
    return url, key, secret


@dataclass
class LiveKitSupervisorSession:
    call_id: str
    room_name: str
    actor: CallActor | None
    lk_session: Any
    _started: bool = False


@dataclass
class LiveKitSupervisor:
    """One LiveKitCallSession per SIP room; webhook is orchestration only."""

    _sessions: dict[str, LiveKitSupervisorSession] = field(default_factory=dict)
    _room_index: dict[str, str] = field(default_factory=dict)
    _start_locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    _closing: set[str] = field(default_factory=set)
    _gateway_urls: Callable[[], tuple[str, str, str]] | None = None

    def set_gateway_urls(self, fn: Callable[[], tuple[str, str, str]]) -> None:
        self._gateway_urls = fn

    def get_session(self, call_id: str) -> LiveKitSupervisorSession | None:
        return self._sessions.get(call_id)

    def get_by_room(self, room_name: str) -> LiveKitSupervisorSession | None:
        cid = self._room_index.get(room_name)
        return self._sessions.get(cid) if cid else None

    async def handle_webhook(self, event: LiveKitWebhookEvent) -> dict[str, str]:
        name = event.event.lower()
        if name == "room_finished":
            if event.room_name in self._room_index:
                await self._close_room(event.room_name, reason="room_finished")
            return {"status": "room_closed"}
        if name == "participant_left":
            return await self._on_participant_left(event)
        if name in {"participant_joined", "participant_connected"}:
            return await self._on_participant_joined(event)
        if name == "track_published":
            return await self._on_track_published(event)
        if name == "participant_connection_aborted":
            await self._close_room(event.room_name, reason="connection_aborted")
            return {"status": "aborted"}
        return {"status": "ignored", "event": event.event}

    async def _on_participant_joined(self, event: LiveKitWebhookEvent) -> dict[str, str]:
        identity = event.participant_identity
        if is_imvera_participant_identity(identity):
            return {"status": "ignored", "reason": "imvera_participant"}
        if not is_sip_participant_kind(event.participant_kind) and not identity:
            return {"status": "ignored", "reason": "not_sip"}
        if event.room_name in self._room_index:
            return {
                "status": "already_active",
                "call_id": self._room_index[event.room_name],
            }
        if os.environ.get("IMVERA_LIVEKIT_MEDIA_GATE") == "1":
            return await self._start_media_gate_session(
                room_name=event.room_name,
                room_sid=event.room_sid,
                sip_identity=identity,
                sip_sid=event.participant_sid,
            )
        return await self._start_session(
            room_name=event.room_name,
            room_sid=event.room_sid,
            sip_identity=identity,
            sip_sid=event.participant_sid,
        )

    async def _on_track_published(self, event: LiveKitWebhookEvent) -> dict[str, str]:
        if is_imvera_participant_identity(event.participant_identity):
            return {"status": "ignored"}
        if event.room_name in self._room_index:
            return {
                "status": "already_active",
                "call_id": self._room_index[event.room_name],
            }
        if not event.participant_identity:
            return {"status": "ignored"}
        if os.environ.get("IMVERA_LIVEKIT_MEDIA_GATE") == "1":
            return await self._start_media_gate_session(
                room_name=event.room_name,
                room_sid=event.room_sid,
                sip_identity=event.participant_identity,
                sip_sid=event.participant_sid,
            )
        return await self._start_session(
            room_name=event.room_name,
            room_sid=event.room_sid,
            sip_identity=event.participant_identity,
            sip_sid=event.participant_sid,
        )

    async def _on_participant_left(self, event: LiveKitWebhookEvent) -> dict[str, str]:
        if is_imvera_participant_identity(event.participant_identity):
            return {"status": "ignored"}
        cid = self._room_index.get(event.room_name)
        if cid is None:
            return {"status": "ignored", "reason": "unknown_room"}
        session = self._sessions.get(cid)
        if session and session.lk_session.phase not in {
            LiveKitSessionPhase.MEDIA_READY,
        }:
            log.info(
                "LiveKit startup abort call_id=%s room_ref=%s phase=%s",
                cid,
                redact_room_name(event.room_name),
                session.lk_session.phase,
            )
        await self._close_room(event.room_name, reason="participant_left")
        return {"status": "closed"}

    async def _start_session(
        self,
        *,
        room_name: str,
        room_sid: str,
        sip_identity: str,
        sip_sid: str,
    ) -> dict[str, str]:
        lock = self._start_locks.setdefault(room_name, asyncio.Lock())
        async with lock:
            if room_name in self._room_index:
                return {
                    "status": "already_active",
                    "call_id": self._room_index[room_name],
                }

            stt, tts, llm = self._gateway_urls() if self._gateway_urls else ("", "", "")
            if stt and tts and llm:
                blockers = await inference_blockers(stt, tts, llm)
                if blockers:
                    log.error("CALL_NOT_READY room_ref=%s blockers=%s", redact_room_name(room_name), blockers)
                    return {"status": "call_not_ready", "blockers": "; ".join(blockers)}

            livekit_url, api_key, api_secret = _livekit_env()
            elder = os.environ.get("IMVERA_ELDER_DISPLAY_NAME", "собеседником")
            call_id = new_imvera_call_id()

            call_id_holder: dict[str, str] = {"id": call_id}
            actor_holder: dict[str, CallActor] = {}

            async def emit_stage(stage: str, **payload: Any) -> None:
                record_event(
                    call_id_holder["id"],
                    RuntimeEvent(
                        call_id_holder["id"],
                        RuntimeEventType.STAGE_TIMING,
                        {"stage": stage, **payload},
                    ),
                )

            async def push_pcm(pcm: bytes, sample_rate: int) -> None:
                await actor_holder["actor"].push_pcm(pcm, sample_rate)

            def note_transport(nbytes: int, rms: float) -> None:
                actor_holder["actor"].note_capture_ingress(nbytes, rms)

            artifact_dir = GATE_ARTIFACT_ROOT / call_id

            lk_session = build_livekit_session(
                room_name=room_name,
                room_sid=room_sid,
                sip_identity=sip_identity,
                sip_sid=sip_sid,
                livekit_url=livekit_url,
                api_key=api_key,
                api_secret=api_secret,
                push_pcm=push_pcm,
                emit_stage=emit_stage,
                note_transport=note_transport,
                artifact_dir=artifact_dir,
                call_id=call_id,
            )

            await emit_stage(
                "livekit.sip_participant.detected",
                room_ref=redact_room_name(room_name),
                room_sid=room_sid,
                participant_ref=redact_sip_identity(sip_identity),
                participant_sid=sip_sid,
            )

            async def send_pcm(pcm: bytes) -> None:
                await lk_session.send_outbound_pcm(pcm, 16000)

            async def flush() -> None:
                await lk_session.flush_outbound()

            async def hangup() -> None:
                await self._close_session(call_id)

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

            async def on_media_ready() -> None:
                await actor.on_media_ready(16000, 640, input_sample_rate=16000)

            lk_session.on_media_ready = on_media_ready

            self._room_index[room_name] = call_id
            await lk_session.start()

            wrapped = LiveKitSupervisorSession(
                call_id=call_id,
                room_name=room_name,
                actor=actor,
                lk_session=lk_session,
                _started=True,
            )
            self._sessions[call_id] = wrapped
            log.info(
                "LiveKit session started call_id=%s room_ref=%s participant_ref=%s",
                call_id,
                redact_room_name(room_name),
                redact_sip_identity(sip_identity),
            )
            return {"status": "started", "call_id": call_id}

    async def _start_media_gate_session(
        self,
        *,
        room_name: str,
        room_sid: str,
        sip_identity: str,
        sip_sid: str,
    ) -> dict[str, str]:
        """Transport-only session — no STT/TTS/LLM/CallActor dialogue."""
        lock = self._start_locks.setdefault(room_name, asyncio.Lock())
        async with lock:
            if room_name in self._room_index:
                return {
                    "status": "already_active",
                    "call_id": self._room_index[room_name],
                }

            livekit_url, api_key, api_secret = _livekit_env()
            call_id = new_imvera_call_id()

            async def emit_stage(stage: str, **payload: Any) -> None:
                record_event(
                    call_id,
                    RuntimeEvent(
                        call_id,
                        RuntimeEventType.STAGE_TIMING,
                        {"stage": stage, **payload},
                    ),
                )

            async def push_pcm(pcm: bytes, sample_rate: int) -> None:
                del pcm, sample_rate

            artifact_dir = GATE_ARTIFACT_ROOT / call_id

            lk_session = build_livekit_session(
                room_name=room_name,
                room_sid=room_sid,
                sip_identity=sip_identity,
                sip_sid=sip_sid,
                livekit_url=livekit_url,
                api_key=api_key,
                api_secret=api_secret,
                push_pcm=push_pcm,
                emit_stage=emit_stage,
                artifact_dir=artifact_dir,
                call_id=call_id,
                media_gate_mode=True,
                publish_outbound=False,
            )

            await emit_stage(
                "livekit.sip_participant.detected",
                room_ref=redact_room_name(room_name),
                room_sid=room_sid,
                participant_ref=redact_sip_identity(sip_identity),
                participant_sid=sip_sid,
                media_gate=True,
            )

            self._room_index[room_name] = call_id
            await lk_session.start()

            wrapped = LiveKitSupervisorSession(
                call_id=call_id,
                room_name=room_name,
                actor=None,
                lk_session=lk_session,
                _started=True,
            )
            self._sessions[call_id] = wrapped
            log.info(
                "LiveKit media-gate session started call_id=%s room_ref=%s",
                call_id,
                redact_room_name(room_name),
            )
            return {"status": "started", "call_id": call_id, "mode": "media_gate"}

    async def _close_room(self, room_name: str, *, reason: str) -> None:
        cid = self._room_index.get(room_name)
        if cid is None:
            return
        await self._close_session(cid, reason=reason)

    async def _close_session(self, call_id: str, *, reason: str = "hangup") -> None:
        if call_id in self._closing:
            return
        self._closing.add(call_id)
        wrapped = self._sessions.pop(call_id, None)
        if wrapped is None:
            self._closing.discard(call_id)
            return
        self._room_index.pop(wrapped.room_name, None)
        await wrapped.lk_session.shutdown()
        if wrapped.actor is not None:
            await wrapped.actor.stop()
        self._closing.discard(call_id)
        log.info("LiveKit session closed call_id=%s reason=%s", call_id, reason)

    def reset_for_tests(self) -> None:
        self._sessions.clear()
        self._room_index.clear()
        self._start_locks.clear()
        self._closing.clear()


_supervisor = LiveKitSupervisor()


def get_livekit_supervisor() -> LiveKitSupervisor:
    return _supervisor
