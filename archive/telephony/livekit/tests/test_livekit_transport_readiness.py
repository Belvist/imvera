"""LiveKit transport vs RX readiness — opening must not wait for inbound PCM."""

from __future__ import annotations

import asyncio

import pytest

from packages.telephony.livekit_readiness import LiveKitReadinessTracker, LiveKitSessionPhase
from packages.telephony.livekit_session import LiveKitCallSession, LiveKitSessionKeys


@pytest.mark.asyncio
async def test_transport_ready_does_not_require_rx_media() -> None:
    tracker = LiveKitReadinessTracker()
    tracker.advance(LiveKitSessionPhase.IMVERA_ROOM_CONNECTED)
    tracker.note_local_track_published()
    tracker.advance(LiveKitSessionPhase.TRANSPORT_READY)

    assert tracker.is_transport_ready()
    assert not tracker.is_rx_media_active()
    assert tracker.timestamps.local_track_published_at is not None
    assert tracker.timestamps.first_inbound_pcm_at is None


@pytest.mark.asyncio
async def test_livekit_opening_does_not_wait_for_inbound_pcm() -> None:
    """Regression: opening callback fires at TRANSPORT_READY without caller PCM."""
    opened = asyncio.Event()
    stages: list[str] = []

    async def push_pcm(pcm: bytes, _sr: int) -> None:
        del pcm

    async def emit_stage(stage: str, **_payload) -> None:
        stages.append(stage)

    async def on_transport_ready() -> None:
        opened.set()

    session = LiveKitCallSession(
        call_id="lk-transport-test",
        keys=LiveKitSessionKeys(room_name="imvera-call-transport"),
        livekit_url="ws://127.0.0.1:7880",
        api_key="devkey",
        api_secret="secret",
        push_pcm=push_pcm,
        emit_stage=emit_stage,
        on_transport_ready=on_transport_ready,
        publish_outbound=False,
    )
    session.readiness.advance(LiveKitSessionPhase.IMVERA_ROOM_CONNECTED)
    await session._maybe_signal_transport_ready()

    assert opened.is_set()
    assert session.phase == LiveKitSessionPhase.TRANSPORT_READY
    assert "livekit.transport_ready" in stages
    assert not session.readiness.is_rx_media_active()


@pytest.mark.asyncio
async def test_livekit_first_inbound_frame_is_not_required_to_answer() -> None:
    """Without caller PCM, session stays alive and transport-ready."""
    async def push_pcm(_pcm: bytes, _sr: int) -> None:
        return

    async def emit_stage(_stage: str, **_payload) -> None:
        return

    session = LiveKitCallSession(
        call_id="lk-no-rx",
        keys=LiveKitSessionKeys(room_name="imvera-call-no-rx"),
        livekit_url="ws://127.0.0.1:7880",
        api_key="devkey",
        api_secret="secret",
        push_pcm=push_pcm,
        emit_stage=emit_stage,
        publish_outbound=False,
    )
    session.readiness.advance(LiveKitSessionPhase.IMVERA_ROOM_CONNECTED)
    await session._maybe_signal_transport_ready()

    await asyncio.sleep(0.05)
    assert session.phase == LiveKitSessionPhase.TRANSPORT_READY
    assert session.readiness.timestamps.first_inbound_pcm_at is None


@pytest.mark.asyncio
async def test_rx_media_active_is_separate_from_transport() -> None:
    stages: list[str] = []

    async def push_pcm(_pcm: bytes, _sr: int) -> None:
        return

    async def emit_stage(stage: str, **_payload) -> None:
        stages.append(stage)

    session = LiveKitCallSession(
        call_id="lk-rx-split",
        keys=LiveKitSessionKeys(room_name="imvera-call-rx"),
        livekit_url="ws://127.0.0.1:7880",
        api_key="devkey",
        api_secret="secret",
        push_pcm=push_pcm,
        emit_stage=emit_stage,
        publish_outbound=False,
    )
    session.readiness.advance(LiveKitSessionPhase.IMVERA_ROOM_CONNECTED)
    await session._signal_transport_ready()
    await session._signal_rx_media_active()

    assert session.phase == LiveKitSessionPhase.RX_MEDIA_ACTIVE
    assert "livekit.transport_ready" in stages
    assert "livekit.inbound.first_frame" in stages
