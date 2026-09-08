"""LiveKit session contract tests — directional invariant + counters."""

from __future__ import annotations

import pytest

from packages.telephony.livekit_counters import LiveKitMediaCounters
from packages.telephony.livekit_session import (
    LiveKitSessionKeys,
    TARGET_SAMPLE_RATE,
    VERA_TRACK_NAME,
)


def test_counters_trace_dict() -> None:
    c = LiveKitMediaCounters()
    c.note_inbound_frame(640)
    c.note_outbound_frame(320)
    d = c.to_trace_dict()
    assert d["transport_rx_frames"] == 1
    assert d["livekit_audio_frames_tx"] == 1


def test_directional_constants() -> None:
    assert TARGET_SAMPLE_RATE == 16000
    assert VERA_TRACK_NAME == "vera-audio"


def test_session_keys() -> None:
    keys = LiveKitSessionKeys(
        room_name="imvera-call-abc",
        sip_participant_identity="sip_user",
    )
    assert keys.room_name.startswith("imvera-call-")


@pytest.mark.asyncio
async def test_shutdown_idempotent() -> None:
    from packages.telephony.livekit_session import LiveKitCallSession

    pcm_log: list[bytes] = []

    async def push_pcm(pcm: bytes, _sr: int) -> None:
        pcm_log.append(pcm)

    async def emit_stage(_stage: str, **_payload) -> None:
        return

    session = LiveKitCallSession(
        call_id="lk-idem",
        keys=LiveKitSessionKeys(room_name="imvera-call-idem"),
        livekit_url="ws://127.0.0.1:7880",
        api_key="devkey",
        api_secret="secret",
        push_pcm=push_pcm,
        emit_stage=emit_stage,
    )
    await session.shutdown()
    await session.shutdown()
    assert session._shutdown_once
