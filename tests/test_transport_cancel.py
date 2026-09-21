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


def test_cancel_mid_pump_session_survives_and_g2_flows() -> None:
    """Barge-in shape: cancel lands mid-send; the pump/WS session must survive
    and the next generation must flow. A normal barge-in NEVER closes the
    media session (no session-killing `stop` on this path)."""
    async def scenario() -> None:
        bridge, ws = _bridge(), _Wire()
        ws.release.clear()
        await bridge.enqueue_outbound_pcm(b"\x01\x00" * 320, generation_id="g-1")
        pump = asyncio.create_task(bridge._pump_outbound_to_ws(ws))
        await asyncio.wait_for(ws.entered.wait(), timeout=2.0)
        ack = bridge.cancel_generation("g-1")
        assert ack["purged_frames"] == 0  # already extracted: in-flight only
        ws.release.set()
        # G2 arrives after the cancel while the same pump is still running.
        for seq in range(3):
            assert await bridge.enqueue_outbound_pcm(
                b"\x02\x00" * 320, generation_id="g-2", sequence=seq
            )
        for _ in range(500):
            if bridge._outbound_queue.empty() and len(ws.sent) >= 4:
                break
            await asyncio.sleep(0.005)
        await asyncio.sleep(0.02)
        pump.cancel()
        try:
            await pump
        except asyncio.CancelledError:
            pass
        # Exactly the bounded in-flight race frame + all of G2.
        assert len(ws.sent) == 4
        assert [g for g, _ in ws.sent[1:]] == ["pcm:02"] * 3
        assert bridge._closed is False
        assert bridge.generation_report("g-2")["sent"] == 3
        # Session still accepts new work after a cancel.
        assert await bridge.enqueue_outbound_pcm(
            b"\x03\x00" * 320, generation_id="g-3"
        ) is True

    asyncio.run(scenario())


def test_request_downstream_stop_uses_break_never_stop(monkeypatch) -> None:
    """request_downstream_stop must use the non-closing `break` primitive:
    `stop` STOPS THE STREAM AND CLOSES the media WS (kills G2 and later)."""
    import packages.telephony.freeswitch_esl as esl_mod

    commands: list[str] = []

    async def fake_api(command: str, *, timeout_s: float = 3.0) -> str:
        commands.append(command)
        return "+OK Success"

    monkeypatch.setattr(esl_mod, "freeswitch_api", fake_api)

    async def scenario() -> None:
        bridge = _bridge()
        ack = await bridge.request_downstream_stop()
        assert commands == [f"uuid_audio_stream {bridge.fs_uuid} break"]
        assert ack["command"] == "uuid_audio_stream break"
        assert ack["ok"] is True
        assert ack["acked_at"] is not None
        assert "Success" in ack["result"]
        assert bridge._closed is False

    asyncio.run(scenario())


def test_request_downstream_stop_failure_is_honest_and_session_open(monkeypatch) -> None:
    """ESL failure is recorded honestly — no exception, no session close.
    The local cancel path (LOCAL_PURGE_ACK) already guaranteed delivery stop."""
    import packages.telephony.freeswitch_esl as esl_mod

    async def fake_api(command: str, *, timeout_s: float = 3.0) -> str:
        raise ConnectionError("ESL unreachable")

    monkeypatch.setattr(esl_mod, "freeswitch_api", fake_api)

    async def scenario() -> None:
        bridge = _bridge()
        ack = await bridge.request_downstream_stop()
        assert ack["acked_at"] is None
        assert "unreachable" in ack["error"]
        assert ack["command"] == "uuid_audio_stream break"
        assert bridge._closed is False
        assert await bridge.enqueue_outbound_pcm(
            b"\x02\x00" * 320, generation_id="g-next"
        ) is True

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


def test_downstream_err_is_not_ack(monkeypatch) -> None:
    """-ERR reply must not produce acked_at (observability bug fix)."""
    import packages.telephony.freeswitch_esl as esl_mod

    async def fake_api(command: str, *, timeout_s: float = 3.0) -> str:
        return "-ERR invalid command"

    monkeypatch.setattr(esl_mod, "freeswitch_api", fake_api)

    async def scenario() -> None:
        bridge = _bridge()
        ack = await bridge.request_downstream_stop()
        assert ack["acked_at"] is None
        assert ack["ok"] is False
        assert "-ERR" in ack["result"]
        assert bridge._closed is False

    asyncio.run(scenario())
