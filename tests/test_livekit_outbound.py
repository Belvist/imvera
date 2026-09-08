"""LiveKit outbound pump tests."""

from __future__ import annotations

import asyncio

import pytest

from packages.telephony.livekit_outbound import LiveKitOutboundPump


class _FakeAudioSource:
    def __init__(self) -> None:
        self.cleared = 0
        self.frames: list[bytes] = []

    def clear_queue(self) -> None:
        self.cleared += 1

    async def capture_frame(self, frame) -> None:
        self.frames.append(bytes(frame.data))

    async def wait_for_playout(self) -> None:
        return


@pytest.mark.asyncio
async def test_outbound_pump_delivers_frames() -> None:
    pump = LiveKitOutboundPump(sample_rate=16000, frame_samples=160)
    source = _FakeAudioSource()
    stages: list[str] = []
    pump.bind_source(
        source,
        emit_stage=lambda stage, **_: stages.append(stage),
        on_frame_sent=lambda _: None,
    )
    pump.start()
    pcm = b"\x01\x00" * 160
    pump.enqueue_pcm(pcm, pump.generation)
    await asyncio.sleep(0.3)
    await pump.stop()
    assert source.frames
    assert any("livekit.outbound.frame" in s for s in stages)


@pytest.mark.asyncio
async def test_clear_bumps_generation_and_drops_stale() -> None:
    pump = LiveKitOutboundPump(sample_rate=16000, frame_samples=320)
    source = _FakeAudioSource()
    pump.bind_source(source)
    pump.start()
    gen0 = pump.generation
    pump.enqueue_pcm(b"\x00\x01" * 320, gen0)
    await pump.clear_playback(source)
    assert source.cleared == 1
    assert pump.generation > gen0
    stale_pcm = b"\xff\x00" * 320
    pump.enqueue_pcm(stale_pcm, gen0)
    await asyncio.sleep(0.2)
    await pump.stop()
    assert not any(b"\xff\x00" in f for f in source.frames)
