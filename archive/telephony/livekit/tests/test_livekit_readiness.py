"""LiveKit session readiness FSM tests."""

import asyncio

import pytest

from packages.telephony.livekit_readiness import LiveKitReadinessTracker, LiveKitSessionPhase


@pytest.mark.asyncio
async def test_track_timeout_fires_when_no_track() -> None:
    tracker = LiveKitReadinessTracker(track_timeout_s=0.05)
    tracker.advance(LiveKitSessionPhase.IMVERA_ROOM_CONNECTED)
    fired = asyncio.Event()

    async def on_timeout() -> None:
        fired.set()

    tracker.start_track_timeout_watch(on_timeout)
    await asyncio.wait_for(fired.wait(), timeout=1.0)
    assert tracker.phase == LiveKitSessionPhase.TRACK_TIMEOUT


@pytest.mark.asyncio
async def test_track_timeout_cancelled_on_subscribe() -> None:
    tracker = LiveKitReadinessTracker(track_timeout_s=0.1)
    tracker.advance(LiveKitSessionPhase.IMVERA_ROOM_CONNECTED)
    tracker.advance(LiveKitSessionPhase.TRACK_SUBSCRIBED)
    tracker.cancel_track_timeout()
    await asyncio.sleep(0.15)
    assert tracker.phase == LiveKitSessionPhase.TRACK_SUBSCRIBED
