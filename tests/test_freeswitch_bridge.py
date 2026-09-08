"""FreeSWITCH bridge session tests."""

from __future__ import annotations

import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect

from packages.telephony.freeswitch_bridge import (
    FreeSwitchBridgeSession,
    FreeSwitchOutboundMode,
)
from packages.telephony.adapter import InboundMediaFrame, StreamTrack
from tools.telephony_gate.tone import generate_tone_s16le, MEDIA_GATE_CALLER_HZ


class _FakeWebSocket:
    def __init__(self, inbound_chunks: list[bytes]) -> None:
        self._inbound = list(inbound_chunks)
        self.sent: list[bytes] = []
        self.sent_text: list[str] = []
        self._idx = 0

    async def receive(self) -> dict:
        if self._idx >= len(self._inbound):
            return {"type": "websocket.disconnect"}
        data = self._inbound[self._idx]
        self._idx += 1
        return {"type": "websocket.receive", "bytes": data}

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(data)

    async def send_text(self, data: str) -> None:
        self.sent_text.append(data)


@pytest.mark.asyncio
async def test_bridge_uplink_only_records_inbound_no_ws_outbound() -> None:
    received: list[InboundMediaFrame] = []

    async def on_inbound(frame: InboundMediaFrame) -> None:
        received.append(frame)

    pcm = generate_tone_s16le(frequency_hz=MEDIA_GATE_CALLER_HZ, duration_s=0.04)
    session = FreeSwitchBridgeSession(
        call_id="fs-test",
        fs_uuid="uuid-1",
        on_inbound=on_inbound,
        uplink_only=True,
    )
    ws = _FakeWebSocket([pcm])
    await session.handle_ws(ws)

    assert len(received) == 1
    assert session.first_inbound_pcm_at is not None
    assert ws.sent == []
    assert ws.sent_text == []


@pytest.mark.asyncio
async def test_bridge_stream_audio_json_sends_text_outbound() -> None:
    received: list[InboundMediaFrame] = []

    async def on_inbound(frame: InboundMediaFrame) -> None:
        received.append(frame)

    pcm = generate_tone_s16le(frequency_hz=MEDIA_GATE_CALLER_HZ, duration_s=0.04)
    out_pcm = generate_tone_s16le(frequency_hz=880.0, duration_s=0.02)
    session = FreeSwitchBridgeSession(
        call_id="fs-test",
        fs_uuid="uuid-1",
        on_inbound=on_inbound,
        uplink_only=False,
        outbound_mode=FreeSwitchOutboundMode.STREAM_AUDIO_JSON,
    )
    ws = _FakeWebSocket([pcm])
    pump = asyncio.create_task(session._pump_outbound_to_ws(ws))
    await session.enqueue_outbound_pcm(out_pcm)
    await asyncio.sleep(0.05)
    pump.cancel()
    try:
        await pump
    except asyncio.CancelledError:
        pass
    await session.close()

    assert len(received) == 0
    assert ws.sent == []
    assert len(ws.sent_text) == 1
    assert '"type":"streamAudio"' in ws.sent_text[0]
    assert '"sampleRate":16000' in ws.sent_text[0]
