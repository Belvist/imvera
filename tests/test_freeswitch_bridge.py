"""FreeSWITCH bridge session tests."""

from __future__ import annotations

import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect

from packages.telephony.freeswitch_bridge import FreeSwitchBridgeSession
from packages.telephony.adapter import InboundMediaFrame, StreamTrack
from tools.telephony_gate.tone import generate_tone_s16le, MEDIA_GATE_CALLER_HZ


class _FakeWebSocket:
    def __init__(self, inbound_chunks: list[bytes]) -> None:
        self._inbound = list(inbound_chunks)
        self.sent: list[bytes] = []
        self._idx = 0

    async def receive(self) -> dict:
        if self._idx >= len(self._inbound):
            return {"type": "websocket.disconnect"}
        data = self._inbound[self._idx]
        self._idx += 1
        return {"type": "websocket.receive", "bytes": data}

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(data)


@pytest.mark.asyncio
async def test_bridge_records_inbound_pcm() -> None:
    received: list[InboundMediaFrame] = []

    async def on_inbound(frame: InboundMediaFrame) -> None:
        received.append(frame)

    pcm = generate_tone_s16le(frequency_hz=MEDIA_GATE_CALLER_HZ, duration_s=0.04)
    session = FreeSwitchBridgeSession(call_id="fs-test", fs_uuid="uuid-1", on_inbound=on_inbound)
    ws = _FakeWebSocket([pcm])

    async def _enqueue_probe() -> None:
        await asyncio.sleep(0.02)
        tone = generate_tone_s16le(frequency_hz=880.0, duration_s=0.04)
        await session.enqueue_outbound_pcm(tone[:640])

    probe = asyncio.create_task(_enqueue_probe())
    await session.handle_ws(ws)
    await probe

    assert len(received) == 1
    assert received[0].track == StreamTrack.INBOUND
    assert session.first_inbound_pcm_at is not None
    assert len(session.raw_inbound_pcm()) > 0
