"""Transport cancel acceptance (P0-B/C): generation identity end-to-end.

Invariant: after cancel ACK, no frame of the cancelled generation may be
handed to the transport sender. Queued ghost frames = 0, late frames = 0,
cross-generation deletion = 0, duplicate cancel side effects = 0.
LOCAL_PURGE_ACK is local only; downstream stop is measured separately.
"""

from __future__ import annotations

import asyncio

import pytest

from packages.telephony.adapter import OutboundAudioFrame
from packages.telephony.freeswitch_bridge import (
    FreeSwitchBridgeSession,
    FreeSwitchOutboundMode,
)

pytestmark = pytest.mark.transport


async def _noop(*_a, **_k):
    return None


class _Wire:
    """Mock websocket: records sent payloads with generation markers."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, int]] = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    async def send_text(self, data: str) -> None:
        import json

        body = json.loads(data)
        self.sent.append((body.get("generation_id", "?"), body.get("sequence", -1)))

    async def send_bytes(self, data: bytes) -> None:
        self.entered.set()
        await self.release.wait()
        # Generation identity never reaches the raw wire: tests distinguish
        # generations by payload marker byte (first byte of the frame).
        self.sent.append((f"pcm:{data[0]:02x}", len(data)))


def _bridge() -> FreeSwitchBridgeSession:
    return FreeSwitchBridgeSession(
        call_id="cancel-acc",
        fs_uuid="uuid-cancel-acc",
        on_inbound=_noop,
        uplink_only=False,
        outbound_mode=FreeSwitchOutboundMode.RAW_BINARY,
    )


def _frame(generation: str, seq: int, pcm: bytes = b"\x01\x00" * 320) -> OutboundAudioFrame:
    return OutboundAudioFrame(
        pcm_s16le=pcm, generation_id=generation, call_id="cancel-acc",
        phrase_id="p", sequence=seq,
    )


async def _drain_pump(bridge: FreeSwitchBridgeSession, ws: _Wire) -> None:
    pump = asyncio.create_task(bridge._pump_outbound_to_ws(ws))
    for _ in range(500):
        if bridge._outbound_queue.empty():
            break
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.02)
    pump.cancel()
    try:
        await pump
    except asyncio.CancelledError:
        pass


def test_enqueue_cancel_pump_sends_nothing() -> None:
    async def scenario() -> None:
        bridge, ws = _bridge(), _Wire()
        for seq in range(5):
            assert await bridge.enqueue_outbound_pcm(
                b"\x01\x00" * 320, generation_id="g-1", sequence=seq
            )
        ack = bridge.cancel_generation("g-1")
        assert ack["purged_frames"] == 5
        assert ack["already_cancelled"] is False
        await _drain_pump(bridge, ws)
        assert ws.sent == []
        report = bridge.generation_report("g-1")
        assert report["sent"] == 0 and report["cancelled"] is True

    asyncio.run(scenario())


def test_pump_race_frame_bounded_and_reported() -> None:
    """Cancel DURING a blocked send: the in-flight frame cannot be recalled
    from the socket — it is bounded to exactly that frame, counted as a
    send race, and downstream stop (not local ACK) owns audible silence."""
    async def scenario() -> None:
        bridge, ws = _bridge(), _Wire()
        ws.release.clear()
        await bridge.enqueue_outbound_pcm(b"\x01\x00" * 320, generation_id="g-1")
        pump = asyncio.create_task(bridge._pump_outbound_to_ws(ws))
        # Pump extracts the frame, then blocks inside send.
        await asyncio.wait_for(ws.entered.wait(), timeout=2.0)
        # Cancel lands while the extracted frame is in flight to the wire.
        ack = bridge.cancel_generation("g-1")
        assert ack["purged_frames"] == 0  # already extracted: queue purge can't help
        ws.release.set()
        await asyncio.sleep(0.05)
        pump.cancel()
        try:
            await pump
        except asyncio.CancelledError:
            pass
        report = bridge.generation_report("g-1")
        # Exactly the in-flight frame escaped; nothing more ever will.
        assert len(ws.sent) == 1
        assert report["sent"] == 1
        assert report["sent_race"] == 1
        assert report["dropped"] == 0
        # Late frames after the race are still rejected.
        assert await bridge.enqueue_outbound_pcm(
            b"\x01\x00" * 320, generation_id="g-1"
        ) is False

    asyncio.run(scenario())


def test_late_chunk_after_cancel_rejected() -> None:
    async def scenario() -> None:
        bridge, ws = _bridge(), _Wire()
        bridge.cancel_generation("g-1")
        assert await bridge.enqueue_outbound_pcm(
            b"\x01\x00" * 320, generation_id="g-1"
        ) is False
        await _drain_pump(bridge, ws)
        assert ws.sent == []
        assert bridge.generation_report("g-1")["dropped"] == 1

    asyncio.run(scenario())


def test_cancel_does_not_touch_next_generation() -> None:
    async def scenario() -> None:
        bridge, ws = _bridge(), _Wire()
        for seq in range(3):
            await bridge.enqueue_outbound_pcm(
                b"\x01\x00" * 320, generation_id="g-1", sequence=seq
            )
            await bridge.enqueue_outbound_pcm(
                b"\x02\x00" * 320, generation_id="g-2", sequence=seq
            )
        ack = bridge.cancel_generation("g-1")
        assert ack["purged_frames"] == 3
        await _drain_pump(bridge, ws)
        assert [g for g, _ in ws.sent] == ["pcm:02", "pcm:02", "pcm:02"]
        assert bridge.generation_report("g-2")["sent"] == 3

    asyncio.run(scenario())


def test_cancel_idempotent_and_unknown_safe() -> None:
    async def scenario() -> None:
        bridge, ws = _bridge(), _Wire()
        first = bridge.cancel_generation("g-x")
        second = bridge.cancel_generation("g-x")
        assert first["already_cancelled"] is False
        assert second["already_cancelled"] is True
        assert second["purged_frames"] == 0
        unknown = bridge.cancel_generation("never-seen")
        assert unknown["purged_frames"] == 0
        await _drain_pump(bridge, ws)
        assert ws.sent == []

    asyncio.run(scenario())


def test_interleaved_generations() -> None:
    async def scenario() -> None:
        bridge, ws = _bridge(), _Wire()
        await bridge.enqueue_outbound_pcm(b"\x01\x00" * 320, generation_id="g-1", sequence=0)
        await bridge.enqueue_outbound_pcm(b"\x02\x00" * 320, generation_id="g-2", sequence=0)
        await bridge.enqueue_outbound_pcm(b"\x01\x00" * 320, generation_id="g-1", sequence=1)
        await bridge.enqueue_outbound_pcm(b"\x02\x00" * 320, generation_id="g-2", sequence=1)
        bridge.cancel_generation("g-1")
        await _drain_pump(bridge, ws)
        assert [g for g, _ in ws.sent] == ["pcm:02", "pcm:02"]
        assert bridge.generation_report("g-1")["sent"] == 0

    asyncio.run(scenario())


def test_close_during_cancel_is_deterministic() -> None:
    async def scenario() -> None:
        bridge, ws = _bridge(), _Wire()
        await bridge.enqueue_outbound_pcm(b"\x01\x00" * 320, generation_id="g-1")
        ack = bridge.cancel_generation("g-1")
        await bridge.close()
        assert await bridge.enqueue_outbound_pcm(
            b"\x01\x00" * 320, generation_id="g-2"
        ) is False
        await _drain_pump(bridge, ws)
        assert ws.sent == []
        assert ack["purged_frames"] == 1

    asyncio.run(scenario())


def test_thousand_cancel_cycles_zero_ghost() -> None:
    async def scenario() -> None:
        bridge, ws = _bridge(), _Wire()
        for cycle in range(1000):
            gid = f"g-{cycle}"
            await bridge.enqueue_outbound_pcm(
                b"\x01\x00" * 320, generation_id=gid, sequence=cycle
            )
            if cycle % 3 == 0:
                bridge.cancel_generation(gid)
        await _drain_pump(bridge, ws)
        assert ws.sent, "no frames survived the cycle storm"
        for cycle in range(1000):
            gid = f"g-{cycle}"
            report = bridge.generation_report(gid)
            if report["cancelled"]:
                assert report["sent"] == 0, f"ghost frame of {gid} reached wire"
                assert report["sent_race"] == 0

    asyncio.run(scenario())
