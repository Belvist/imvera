"""LiveKit session readiness FSM — webhook ≠ media ready (ADR-012)."""

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
    MEDIA_READY = "media_ready"
    TRACK_TIMEOUT = "track_timeout"
    ABORTED = "aborted"


@dataclass
class LiveKitReadinessTracker:
    """Tracks startup FSM; MEDIA_READY only after subscribed SIP audio track delivers frames."""

    track_timeout_s: float = 15.0
    phase: LiveKitSessionPhase = LiveKitSessionPhase.PARTICIPANT_DETECTED
    _media_ready: asyncio.Event = field(default_factory=asyncio.Event)
    _track_timer: asyncio.Task | None = None
    _room_connected_mono: float | None = None

    def advance(self, phase: LiveKitSessionPhase) -> LiveKitSessionPhase:
        self.phase = phase
        if phase == LiveKitSessionPhase.IMVERA_ROOM_CONNECTED:
            self._room_connected_mono = time.monotonic()
        if phase == LiveKitSessionPhase.MEDIA_READY:
            self._media_ready.set()
        return phase

    def is_media_ready(self) -> bool:
        return self.phase == LiveKitSessionPhase.MEDIA_READY

    def start_track_timeout_watch(self, on_timeout) -> None:
        if self._track_timer and not self._track_timer.done():
            return

        async def _watch() -> None:
            await asyncio.sleep(self.track_timeout_s)
            if self.phase in {
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

    async def wait_media_ready(self, timeout_s: float = 20.0) -> bool:
        try:
            await asyncio.wait_for(self._media_ready.wait(), timeout=timeout_s)
            return True
        except asyncio.TimeoutError:
            return False
