"""LiveKit call session — one SIP participant ↔ one CallActor (livekit.rtc only)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import wave
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packages.telephony.adapter import InboundMediaFrame, StreamTrack
from packages.telephony.livekit_counters import LiveKitInboundFrameStats, LiveKitMediaCounters
from packages.telephony.livekit_outbound import LiveKitOutboundPump
from packages.telephony.livekit_privacy import new_imvera_call_id, redact_room_name, redact_sip_identity
from packages.telephony.livekit_readiness import LiveKitReadinessTracker, LiveKitSessionPhase
from packages.voice_runtime.audio import pcm_rms_s16le

log = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000
VERA_TRACK_NAME = "vera-audio"
IMVERA_IDENTITY_PREFIX = os.environ.get("IMVERA_LIVEKIT_IDENTITY_PREFIX", "imvera-runtime")
DEFAULT_TRACK_TIMEOUT_S = float(os.environ.get("IMVERA_LIVEKIT_TRACK_TIMEOUT_S", "15"))

EmitStageFn = Callable[[str, dict[str, Any]], Awaitable[None]]
PushPcmFn = Callable[[bytes, int], Awaitable[None]]
NoteTransportFn = Callable[[int, float], None]
MediaReadyFn = Callable[[], Awaitable[None]]


def is_imvera_participant_identity(identity: str) -> bool:
    return identity.startswith(IMVERA_IDENTITY_PREFIX)


def is_sip_participant_kind(kind: int) -> bool:
    return kind == 3


@dataclass
class LiveKitSessionKeys:
    room_name: str
    room_sid: str = ""
    sip_participant_identity: str = ""
    sip_participant_sid: str = ""


@dataclass
class LiveKitCallSession:
    """One LiveKit room SIP caller ↔ IMVERA CallActor."""

    call_id: str
    keys: LiveKitSessionKeys
    livekit_url: str
    api_key: str
    api_secret: str
    push_pcm: PushPcmFn
    emit_stage: EmitStageFn
    note_transport: NoteTransportFn | None = None
    on_media_ready: MediaReadyFn | None = None
    artifact_dir: Path | None = None
    counters: LiveKitMediaCounters = field(default_factory=LiveKitMediaCounters)
    inbound_stats: LiveKitInboundFrameStats = field(default_factory=LiveKitInboundFrameStats)
    readiness: LiveKitReadinessTracker = field(
        default_factory=lambda: LiveKitReadinessTracker(track_timeout_s=DEFAULT_TRACK_TIMEOUT_S)
    )
    _room: Any = None
    _audio_source: Any = None
    _local_track: Any = None
    _outbound_pump: LiveKitOutboundPump = field(default_factory=LiveKitOutboundPump)
    _inbound_task: asyncio.Task | None = None
    _started: bool = False
    _shutdown: bool = False
    _shutdown_once: bool = False
    _raw_inbound: bytearray = field(default_factory=bytearray)
    _vera_outbound: bytearray = field(default_factory=bytearray)
    _sip_track_sid: str = ""
    _media_ready_fired: bool = False

    @property
    def phase(self) -> LiveKitSessionPhase:
        return self.readiness.phase

    async def start(self) -> None:
        if self._started or self._shutdown:
            return
        self._started = True
        from livekit import rtc
        from livekit.api import AccessToken, VideoGrants

        self.readiness.advance(LiveKitSessionPhase.PARTICIPANT_DETECTED)
        self.readiness.start_track_timeout_watch(self._on_track_timeout)

        token = (
            AccessToken(self.api_key, self.api_secret)
            .with_identity(f"{IMVERA_IDENTITY_PREFIX}-{self.call_id}")
            .with_name("IMVERA")
            .with_grants(
                VideoGrants(
                    room_join=True,
                    room=self.keys.room_name,
                    can_publish=True,
                    can_subscribe=True,
                )
            )
            .to_jwt()
        )
        self._room = rtc.Room()
        self._room.on("track_subscribed", self._on_track_subscribed)
        self._room.on("track_published", self._on_track_published)
        self._room.on("participant_disconnected", self._on_participant_disconnected)
        await self._room.connect(self.livekit_url, token)
        self.readiness.advance(LiveKitSessionPhase.IMVERA_ROOM_CONNECTED)
        await self.emit_stage(
            "livekit.room.connected",
            room_ref=redact_room_name(self.keys.room_name),
            room_sid=self.keys.room_sid,
            call_id=self.call_id,
        )
        self._audio_source = rtc.AudioSource(TARGET_SAMPLE_RATE, 1, queue_size_ms=200)
        self._local_track = rtc.LocalAudioTrack.create_audio_track(VERA_TRACK_NAME, self._audio_source)
        self._outbound_pump.bind_source(
            self._audio_source,
            emit_stage=self.emit_stage,
            on_frame_sent=lambda n: self._on_outbound_bytes(n),
        )
        self._outbound_pump.start()
        await self._room.local_participant.publish_track(self._local_track)
        await self.emit_stage(
            "livekit.outbound.track_published",
            track_name=VERA_TRACK_NAME,
            room_ref=redact_room_name(self.keys.room_name),
        )
        await self._subscribe_existing_sip_tracks()

    async def _on_track_timeout(self) -> None:
        if self._shutdown:
            return
        await self.emit_stage(
            "livekit.track_timeout",
            call_id=self.call_id,
            room_ref=redact_room_name(self.keys.room_name),
            phase=str(self.readiness.phase),
        )
        await self.shutdown()

    def _on_track_published(
        self,
        publication: Any,
        participant: Any,
    ) -> None:
        if is_imvera_participant_identity(participant.identity):
            return
        from livekit import rtc

        if publication.kind != rtc.TrackKind.KIND_AUDIO:
            return
        if self.readiness.phase in {
            LiveKitSessionPhase.SIP_AUDIO_TRACK_AVAILABLE,
            LiveKitSessionPhase.TRACK_SUBSCRIBED,
            LiveKitSessionPhase.MEDIA_READY,
        }:
            return
        self.readiness.advance(LiveKitSessionPhase.SIP_AUDIO_TRACK_AVAILABLE)
        asyncio.create_task(
            self.emit_stage(
                "livekit.sip_audio_track.available",
                call_id=self.call_id,
                participant_sid=participant.sid,
                participant_ref=redact_sip_identity(participant.identity),
                track_sid=publication.sid,
            )
        )

    async def _subscribe_existing_sip_tracks(self) -> None:
        if self._room is None:
            return
        for participant in self._room.remote_participants.values():
            if is_imvera_participant_identity(participant.identity):
                continue
            if self.keys.sip_participant_identity and participant.identity != self.keys.sip_participant_identity:
                continue
            for pub in participant.track_publications.values():
                from livekit import rtc

                if pub.kind == rtc.TrackKind.KIND_AUDIO and pub.track:
                    if self.readiness.phase == LiveKitSessionPhase.IMVERA_ROOM_CONNECTED:
                        self.readiness.advance(LiveKitSessionPhase.SIP_AUDIO_TRACK_AVAILABLE)
                    await self._start_inbound_stream(pub.track, participant)

    def _on_track_subscribed(
        self,
        track: Any,
        publication: Any,
        participant: Any,
    ) -> None:
        if is_imvera_participant_identity(participant.identity):
            return
        from livekit import rtc

        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        if self.keys.sip_participant_identity and participant.identity != self.keys.sip_participant_identity:
            return
        asyncio.create_task(self._start_inbound_stream(track, participant))

    async def _start_inbound_stream(self, track: Any, participant: Any) -> None:
        if self._inbound_task and not self._inbound_task.done():
            return
        self.keys.sip_participant_identity = participant.identity
        self.keys.sip_participant_sid = participant.sid
        self._sip_track_sid = track.sid
        self.counters.livekit_track_subscribed += 1
        self.readiness.advance(LiveKitSessionPhase.TRACK_SUBSCRIBED)
        self.readiness.cancel_track_timeout()
        await self.emit_stage(
            "livekit.track.subscribed",
            call_id=self.call_id,
            participant_sid=participant.sid,
            participant_ref=redact_sip_identity(participant.identity),
            track_sid=track.sid,
        )
        self._inbound_task = asyncio.create_task(
            self._pump_inbound(track, participant),
            name=f"livekit-inbound-{self.call_id}",
        )

    async def _signal_media_ready(self) -> None:
        if self._media_ready_fired or self._shutdown:
            return
        self._media_ready_fired = True
        self.readiness.advance(LiveKitSessionPhase.MEDIA_READY)
        await self.emit_stage("livekit.media_ready", call_id=self.call_id)
        if self.on_media_ready is not None:
            await self.on_media_ready()

    async def _pump_inbound(self, track: Any, participant: Any) -> None:
        from livekit import rtc

        stream = rtc.AudioStream(
            track,
            sample_rate=TARGET_SAMPLE_RATE,
            num_channels=1,
        )
        try:
            async for event in stream:
                if self._shutdown:
                    break
                frame = event.frame
                pcm = bytes(frame.data)
                if not pcm:
                    continue
                if not self.readiness.is_media_ready():
                    await self._signal_media_ready()
                received_at = time.monotonic()
                rms = round(pcm_rms_s16le(pcm), 1)
                peak = 0
                if len(pcm) >= 2:
                    peak = max(
                        abs(int.from_bytes(pcm[i : i + 2], "little", signed=True))
                        for i in range(0, len(pcm) - 1, 2)
                    )
                seq = self.inbound_stats.record(len(pcm), rms, peak)
                self.counters.note_inbound_frame(len(pcm))
                self.counters.actor_pcm_bytes += len(pcm)
                self._raw_inbound.extend(pcm)
                if self.note_transport:
                    self.note_transport(len(pcm), rms)
                await self.emit_stage(
                    "livekit.inbound.frame",
                    call_id=self.call_id,
                    participant_sid=participant.sid,
                    track_sid=track.sid,
                    seq=seq,
                    received_at=received_at,
                    sample_rate=TARGET_SAMPLE_RATE,
                    channels=1,
                    bytes=len(pcm),
                    rms=rms,
                    peak=peak,
                )
                frame_obj = InboundMediaFrame(
                    pcm_s16le=pcm,
                    sample_rate=TARGET_SAMPLE_RATE,
                    track=StreamTrack.INBOUND,
                    call_id=self.call_id,
                    carrier_call_ref=track.sid,
                )
                await self.push_pcm(frame_obj.pcm_s16le, frame_obj.sample_rate)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("LiveKit inbound pump ended call_id=%s: %s", self.call_id, exc)
        finally:
            await stream.aclose()

    def _on_outbound_bytes(self, nbytes: int) -> None:
        self.counters.note_outbound_frame(nbytes)

    async def send_outbound_pcm(self, pcm16le: bytes, _source_sample_rate: int = TARGET_SAMPLE_RATE) -> None:
        if self._shutdown:
            return
        self._vera_outbound.extend(pcm16le)
        self._outbound_pump.enqueue_pcm(pcm16le, self._outbound_pump.generation)

    async def flush_outbound(self) -> None:
        if self._audio_source is None:
            return
        await self._outbound_pump.clear_playback(self._audio_source)

    async def shutdown(self) -> None:
        if self._shutdown_once:
            return
        self._shutdown_once = True
        self._shutdown = True
        self.readiness.cancel_track_timeout()
        if self.readiness.phase not in {
            LiveKitSessionPhase.TRACK_TIMEOUT,
            LiveKitSessionPhase.ABORTED,
        }:
            if not self.readiness.is_media_ready():
                self.readiness.advance(LiveKitSessionPhase.ABORTED)
        if self._inbound_task and not self._inbound_task.done():
            self._inbound_task.cancel()
            try:
                await self._inbound_task
            except asyncio.CancelledError:
                pass
        await self._outbound_pump.stop()
        if self._room is not None:
            try:
                await self._room.disconnect()
            except Exception:
                pass
            await self.emit_stage(
                "livekit.room.disconnected",
                room_ref=redact_room_name(self.keys.room_name),
                call_id=self.call_id,
            )
        self._write_artifacts()
        self._started = False

    def _on_participant_disconnected(self, participant: Any) -> None:
        if participant.identity == self.keys.sip_participant_identity:
            asyncio.create_task(self._handle_sip_left(participant))

    async def _handle_sip_left(self, participant: Any) -> None:
        await self.emit_stage(
            "livekit.participant.left",
            call_id=self.call_id,
            participant_sid=participant.sid,
            participant_ref=redact_sip_identity(participant.identity),
        )
        await self.shutdown()

    def _write_artifacts(self) -> None:
        if self.artifact_dir is None:
            return
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        if self._raw_inbound:
            self._write_wav(self.artifact_dir / "raw_inbound.wav", bytes(self._raw_inbound))
        if self._vera_outbound:
            self._write_wav(self.artifact_dir / "vera_outbound.wav", bytes(self._vera_outbound))

    @staticmethod
    def _write_wav(path: Path, pcm: bytes) -> None:
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(TARGET_SAMPLE_RATE)
            wf.writeframes(pcm)

    def pipeline_trace(self) -> dict[str, int]:
        return self.counters.to_trace_dict()


# Backward-compatible alias
new_livekit_call_id = new_imvera_call_id
