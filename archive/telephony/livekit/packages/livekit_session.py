"""LiveKit call session — one SIP participant ↔ one CallActor (livekit.rtc only)."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
import wave
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packages.telephony.adapter import InboundMediaFrame, StreamTrack
from packages.telephony.livekit_counters import LiveKitInboundFrameStats, LiveKitMediaCounters
from packages.telephony.livekit_gate_evidence import MediaGateEvidence, write_evidence
from packages.telephony.livekit_gate_tone import MEDIA_GATE_PROBE_OUTBOUND_HZ
from packages.telephony.livekit_outbound import LiveKitOutboundPump
from packages.telephony.livekit_privacy import new_imvera_call_id, redact_room_name, redact_sip_identity
from packages.telephony.livekit_readiness import LiveKitReadinessTracker, LiveKitSessionPhase
from packages.voice_runtime.audio import pcm_rms_s16le

log = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000
VERA_TRACK_NAME = "vera-audio"
GATE_SYNTHETIC_DOWNLINK = Path(".run/livekit-gate/synthetic_downlink.u8")
IMVERA_IDENTITY_PREFIX = os.environ.get("IMVERA_LIVEKIT_IDENTITY_PREFIX", "imvera-runtime")
DEFAULT_TRACK_TIMEOUT_S = float(os.environ.get("IMVERA_LIVEKIT_TRACK_TIMEOUT_S", "15"))

EmitStageFn = Callable[[str, dict[str, Any]], Awaitable[None]]
PushPcmFn = Callable[[bytes, int], Awaitable[None]]
NoteTransportFn = Callable[[int, float], None]
TransportReadyFn = Callable[[], Awaitable[None]]
InboundMediaActiveFn = Callable[[], Awaitable[None]]
# Backward-compatible alias for supervisor/tests.
MediaReadyFn = TransportReadyFn


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
    on_transport_ready: TransportReadyFn | None = None
    on_inbound_media_active: InboundMediaActiveFn | None = None
    on_media_ready: TransportReadyFn | None = None
    artifact_dir: Path | None = None
    media_gate_mode: bool = False
    publish_outbound: bool = True
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
    _transport_ready_fired: bool = False
    _rx_media_active_fired: bool = False
    _rx_speech_active_fired: bool = False
    _first_outbound_frame_emitted: bool = False
    _first_livekit_frame_at: float | None = None
    _first_imvera_pcm_at: float | None = None
    _probe_outbound_task: asyncio.Task | None = None

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
        if self.publish_outbound:
            self._audio_source = rtc.AudioSource(TARGET_SAMPLE_RATE, 1, queue_size_ms=200)
            track_name = "gate-probe-audio" if self.media_gate_mode else VERA_TRACK_NAME
            self._local_track = rtc.LocalAudioTrack.create_audio_track(track_name, self._audio_source)
            self._outbound_pump.bind_source(
                self._audio_source,
                emit_stage=self.emit_stage,
                on_frame_sent=lambda n: self._on_outbound_bytes(n),
            )
            self._outbound_pump.start()
            await self._room.local_participant.publish_track(self._local_track)
            self.readiness.note_local_track_published()
            await self.emit_stage(
                "livekit.local_track.published",
                track_name=track_name,
                room_ref=redact_room_name(self.keys.room_name),
                media_gate_probe=self.media_gate_mode,
            )
            await self._maybe_signal_transport_ready()
            if self.media_gate_mode:
                self._probe_outbound_task = asyncio.create_task(
                    self._pump_probe_outbound_tone(MEDIA_GATE_PROBE_OUTBOUND_HZ),
                    name=f"livekit-probe-out-{self.call_id}",
                )
        await self._subscribe_existing_sip_tracks()
        await self._maybe_signal_transport_ready()

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
            LiveKitSessionPhase.TRANSPORT_READY,
            LiveKitSessionPhase.RX_MEDIA_ACTIVE,
            LiveKitSessionPhase.RX_SPEECH_ACTIVE,
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
            "livekit.remote_track.subscribed",
            call_id=self.call_id,
            participant_sid=participant.sid,
            participant_ref=redact_sip_identity(participant.identity),
            track_sid=track.sid,
        )
        self._inbound_task = asyncio.create_task(
            self._pump_inbound(track, participant),
            name=f"livekit-inbound-{self.call_id}",
        )
        await self._maybe_signal_transport_ready()

    async def _maybe_signal_transport_ready(self) -> None:
        if self._transport_ready_fired or self._shutdown:
            return
        if self.readiness.phase == LiveKitSessionPhase.PARTICIPANT_DETECTED:
            return
        if self.publish_outbound and self._local_track is None:
            return
        await self._signal_transport_ready()

    async def _signal_transport_ready(self) -> None:
        if self._transport_ready_fired or self._shutdown:
            return
        self._transport_ready_fired = True
        self.readiness.advance(LiveKitSessionPhase.TRANSPORT_READY)
        self.readiness.cancel_track_timeout()
        await self.emit_stage(
            "livekit.transport_ready",
            call_id=self.call_id,
            **self.readiness.timestamps.to_trace_dict(),
        )
        callback = self.on_transport_ready or self.on_media_ready
        if callback is not None:
            await callback()

    async def _signal_rx_media_active(self) -> None:
        if self._rx_media_active_fired or self._shutdown:
            return
        self._rx_media_active_fired = True
        self.readiness.advance(LiveKitSessionPhase.RX_MEDIA_ACTIVE)
        await self.emit_stage(
            "livekit.inbound.first_frame",
            call_id=self.call_id,
            **self.readiness.timestamps.to_trace_dict(),
        )
        if self.on_inbound_media_active is not None:
            await self.on_inbound_media_active()

    async def _signal_rx_speech_active(self) -> None:
        if self._rx_speech_active_fired or self._shutdown:
            return
        self._rx_speech_active_fired = True
        self.readiness.advance(LiveKitSessionPhase.RX_SPEECH_ACTIVE)
        await self.emit_stage(
            "livekit.inbound.first_nonzero_frame",
            call_id=self.call_id,
            **self.readiness.timestamps.to_trace_dict(),
        )

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
                if self._first_livekit_frame_at is None:
                    self._first_livekit_frame_at = time.time()
                if not self.readiness.is_rx_media_active():
                    await self._signal_rx_media_active()
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
                self.counters.actor_pcm_frames += 1
                if peak > 50 or rms > 50.0:
                    self.counters.nonzero_pcm_frames += 1
                    if self._first_imvera_pcm_at is None:
                        self._first_imvera_pcm_at = time.time()
                    if not self._rx_speech_active_fired:
                        await self._signal_rx_speech_active()
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
        if nbytes <= 0 or self._first_outbound_frame_emitted:
            return
        self._first_outbound_frame_emitted = True
        self.readiness.note_first_outbound_pcm()
        asyncio.create_task(
            self.emit_stage(
                "livekit.outbound.first_frame",
                call_id=self.call_id,
                bytes=nbytes,
                **self.readiness.timestamps.to_trace_dict(),
            )
        )

    async def send_outbound_pcm(self, pcm16le: bytes, _source_sample_rate: int = TARGET_SAMPLE_RATE) -> None:
        if self._shutdown:
            return
        self._vera_outbound.extend(pcm16le)
        self._outbound_pump.enqueue_pcm(pcm16le, self._outbound_pump.generation)

    async def flush_outbound(self) -> None:
        if self._audio_source is None:
            return
        await self._outbound_pump.clear_playback(self._audio_source)

    async def wait_outbound_playout(self) -> None:
        if self._audio_source is None:
            return
        await self._outbound_pump.wait_drained(
            self._audio_source,
            self._outbound_pump.generation,
        )

    async def _pump_probe_outbound_tone(self, frequency_hz: float) -> None:
        chunk_ms = 20
        samples_per_chunk = TARGET_SAMPLE_RATE * chunk_ms // 1000
        phase = 0
        try:
            while not self._shutdown:
                pcm = bytearray()
                for i in range(samples_per_chunk):
                    sample = int(
                        8192.0
                        * math.sin(2.0 * math.pi * frequency_hz * (phase + i) / TARGET_SAMPLE_RATE)
                    )
                    pcm.extend(int(sample).to_bytes(2, "little", signed=True))
                phase += samples_per_chunk
                await self.send_outbound_pcm(bytes(pcm), TARGET_SAMPLE_RATE)
                await asyncio.sleep(chunk_ms / 1000.0)
        except asyncio.CancelledError:
            raise

    async def shutdown(self) -> None:
        if self._shutdown_once:
            return
        self._shutdown_once = True
        self._shutdown = True
        self.readiness.cancel_track_timeout()
        if self._probe_outbound_task and not self._probe_outbound_task.done():
            self._probe_outbound_task.cancel()
            try:
                await self._probe_outbound_task
            except asyncio.CancelledError:
                pass
        if self.readiness.phase not in {
            LiveKitSessionPhase.TRACK_TIMEOUT,
            LiveKitSessionPhase.ABORTED,
        }:
            if not self.readiness.is_transport_ready():
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
        if self.media_gate_mode:
            self._write_media_gate_evidence()
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

    def _write_media_gate_evidence(self) -> None:
        if self.artifact_dir is None:
            return
        invite_meta = self._load_synthetic_invite_meta()
        peak = max((p for _, _, p in self.inbound_stats.frames), default=0)
        rms_peak = max((r for _, r, _ in self.inbound_stats.frames), default=0.0)
        synthetic_tx_packets = int(
            invite_meta.get("synthetic_rtp_tx_packets", invite_meta.get("sip_rtp_tx_packets", 0))
        )
        synthetic_tx_bytes = int(
            invite_meta.get("synthetic_rtp_tx_bytes", invite_meta.get("sip_rtp_tx_bytes", 0))
        )
        downlink = str(GATE_SYNTHETIC_DOWNLINK) if GATE_SYNTHETIC_DOWNLINK.exists() else ""
        evidence = MediaGateEvidence(
            call_id=self.call_id,
            room_ref=redact_room_name(self.keys.room_name),
            room_sid=self.keys.room_sid,
            sip_participant_sid=self.keys.sip_participant_sid,
            remote_track_sid=self._sip_track_sid,
            invite_sent_at=invite_meta.get("invite_sent_at"),
            sip_answered_at=invite_meta.get("sip_answered_at"),
            room_connected_at=self.readiness.timestamps.room_connected_at,
            local_track_published_at=self.readiness.timestamps.local_track_published_at,
            transport_ready_at=self.readiness.timestamps.transport_ready_at,
            first_outbound_pcm_at=self.readiness.timestamps.first_outbound_pcm_at,
            first_livekit_frame_at=self._first_livekit_frame_at,
            first_imvera_pcm_at=self._first_imvera_pcm_at,
            first_inbound_pcm_at=self.readiness.timestamps.first_inbound_pcm_at,
            synthetic_rtp_tx_packets=synthetic_tx_packets,
            synthetic_rtp_tx_bytes=synthetic_tx_bytes,
            livekit_track_frames=self.counters.livekit_audio_frames_rx,
            livekit_track_bytes=self.counters.livekit_audio_bytes_rx,
            livekit_outbound_frames=self.counters.livekit_audio_frames_tx,
            livekit_outbound_bytes=self.counters.livekit_audio_bytes_tx,
            actor_pcm_frames=self.counters.actor_pcm_frames,
            actor_pcm_bytes=self.counters.actor_pcm_bytes,
            nonzero_pcm_frames=self.counters.nonzero_pcm_frames,
            inbound_rms_peak=rms_peak,
            inbound_peak_sample=peak,
            raw_inbound_wav=str(self.artifact_dir / "raw_inbound.wav"),
            synthetic_downlink_wav=downlink,
            negotiated_codecs=list(invite_meta.get("negotiated_codecs", [])),
        )
        write_evidence(self.artifact_dir / "media_gate_evidence.json", evidence)

    @staticmethod
    def _load_synthetic_invite_meta() -> dict:
        meta_path = Path(".run/livekit-gate/synthetic_invite.json")
        if not meta_path.exists():
            return {}
        import json

        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

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
