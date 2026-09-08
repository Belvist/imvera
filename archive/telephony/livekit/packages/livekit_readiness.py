"""LiveKit session readiness FSM — transport vs RX are separate (ADR-012)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import StrEnum


class LiveKitSessionPhase(StrEnum):
    PARTICIPANT_DETECTED = "participant_detected"
    IMVERA_ROOM_CONNECTED = "imvera_room_connected"
    SIP_AUDIO_TRACK_AVAILABLE = "sip_audio_track_available"
    TRACK_SUBSCRIBED = "track_subscribed"
    TRANSPORT_READY = "transport_ready"
    RX_MEDIA_ACTIVE = "rx_media_active"
    RX_SPEECH_ACTIVE = "rx_speech_active"
    # Backward-compatible alias — do not use for gating opening.
    MEDIA_READY = "media_ready"
    TRACK_TIMEOUT = "track_timeout"
    ABORTED = "aborted"


@dataclass
class LiveKitReadinessTimestamps:
    invite_at: float | None = None
    sip_participant_at: float | None = None
    room_connected_at: float | None = None
    remote_track_at: float | None = None
    local_track_published_at: float | None = None
    transport_ready_at: float | None = None
    first_outbound_pcm_at: float | None = None
    first_inbound_pcm_at: float | None = None
    first_nonzero_inbound_at: float | None = None

    def to_trace_dict(self) -> dict[str, float | None]:
        return {
            "invite_at": self.invite_at,
            "sip_participant_at": self.sip_participant_at,
            "room_connected_at": self.room_connected_at,
            "remote_track_at": self.remote_track_at,
            "local_track_published_at": self.local_track_published_at,
            "transport_ready_at": self.transport_ready_at,
            "first_outbound_pcm_at": self.first_outbound_pcm_at,
            "first_inbound_pcm_at": self.first_inbound_pcm_at,
            "first_nonzero_inbound_at": self.first_nonzero_inbound_at,
        }


@dataclass
class LiveKitReadinessTracker:
    """Opening gates on TRANSPORT_READY; inbound RX tracked separately."""

    track_timeout_s: float = 15.0
    phase: LiveKitSessionPhase = LiveKitSessionPhase.PARTICIPANT_DETECTED
    timestamps: LiveKitReadinessTimestamps = field(default_factory=LiveKitReadinessTimestamps)
    _transport_ready: asyncio.Event = field(default_factory=asyncio.Event)
    _rx_media_active: asyncio.Event = field(default_factory=asyncio.Event)
    _track_timer: asyncio.Task | None = None
    _room_connected_mono: float | None = None

    def advance(self, phase: LiveKitSessionPhase) -> LiveKitSessionPhase:
        now = time.time()
        self.phase = phase
        if phase == LiveKitSessionPhase.PARTICIPANT_DETECTED:
            self.timestamps.sip_participant_at = now
        if phase == LiveKitSessionPhase.IMVERA_ROOM_CONNECTED:
            self._room_connected_mono = time.monotonic()
            self.timestamps.room_connected_at = now
        if phase == LiveKitSessionPhase.TRACK_SUBSCRIBED:
            self.timestamps.remote_track_at = now
        if phase == LiveKitSessionPhase.TRANSPORT_READY:
            self.timestamps.transport_ready_at = now
            self._transport_ready.set()
        if phase == LiveKitSessionPhase.RX_MEDIA_ACTIVE:
            self.timestamps.first_inbound_pcm_at = now
            self._rx_media_active.set()
        if phase == LiveKitSessionPhase.RX_SPEECH_ACTIVE:
            self.timestamps.first_nonzero_inbound_at = now
        return phase

    def note_local_track_published(self) -> None:
        self.timestamps.local_track_published_at = time.time()

    def note_first_outbound_pcm(self) -> None:
        if self.timestamps.first_outbound_pcm_at is None:
            self.timestamps.first_outbound_pcm_at = time.time()

    def note_invite_at(self, when: float | None = None) -> None:
        self.timestamps.invite_at = when if when is not None else time.time()

    def is_transport_ready(self) -> bool:
        return self.phase in {
            LiveKitSessionPhase.TRANSPORT_READY,
            LiveKitSessionPhase.RX_MEDIA_ACTIVE,
            LiveKitSessionPhase.RX_SPEECH_ACTIVE,
            LiveKitSessionPhase.MEDIA_READY,
        }

    def is_rx_media_active(self) -> bool:
        return self.phase in {
            LiveKitSessionPhase.RX_MEDIA_ACTIVE,
            LiveKitSessionPhase.RX_SPEECH_ACTIVE,
            LiveKitSessionPhase.MEDIA_READY,
        }

    # Backward-compatible helpers (opening must NOT use these).
    def is_media_ready(self) -> bool:
        return self.is_rx_media_active()

    def start_track_timeout_watch(self, on_timeout) -> None:
        if self._track_timer and not self._track_timer.done():
            return

        async def _watch() -> None:
            await asyncio.sleep(self.track_timeout_s)
            if self.phase in {
                LiveKitSessionPhase.TRANSPORT_READY,
                LiveKitSessionPhase.RX_MEDIA_ACTIVE,
                LiveKitSessionPhase.RX_SPEECH_ACTIVE,
                LiveKitSessionPhase.MEDIA_READY,
                LiveKitSessionPhase.ABORTED,
                LiveKitSessionPhase.TRACK_TIMEOUT,
            }:
                return
            if self.phase in {
                LiveKitSessionPhase.TRACK_SUBSCRIBED,
                LiveKitSessionPhase.SIP_AUDIO_TRACK_AVAILABLE,
            }:
                return
            self.advance(LiveKitSessionPhase.TRACK_TIMEOUT)
            await on_timeout()

        self._track_timer = asyncio.create_task(_watch(), name="livekit-track-timeout")

    def cancel_track_timeout(self) -> None:
        if self._track_timer and not self._track_timer.done():
            self._track_timer.cancel()

    async def wait_transport_ready(self, timeout_s: float = 20.0) -> bool:
        try:
            await asyncio.wait_for(self._transport_ready.wait(), timeout=timeout_s)
            return True
        except asyncio.TimeoutError:
            return False

    async def wait_rx_media_active(self, timeout_s: float = 20.0) -> bool:
        try:
            await asyncio.wait_for(self._rx_media_active.wait(), timeout=timeout_s)
            return True
        except asyncio.TimeoutError:
            return False

    async def wait_media_ready(self, timeout_s: float = 20.0) -> bool:
        return await self.wait_rx_media_active(timeout_s)
