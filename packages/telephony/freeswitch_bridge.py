"""FreeSWITCH PCM WebSocket bridge — directional READ/WRITE legs (ADR-013).

P0 validation may use mod_audio_stream (community uplink; bidirectional requires
commercial edition or future mod_imvera_audio). This module is transport-only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from packages.telephony.adapter import (
    InboundMediaFrame,
    StreamTrack,
    TelephonyMediaCounters,
)

log = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000
FRAME_MS = 20


PushInboundFn = Callable[[InboundMediaFrame], Awaitable[None]]


@dataclass
class FreeSwitchBridgeSession:
    """One call UUID ↔ bidirectional PCM over WebSocket."""

    call_id: str
    fs_uuid: str
    on_inbound: PushInboundFn
    sample_rate: int = TARGET_SAMPLE_RATE
    counters: TelephonyMediaCounters = field(default_factory=TelephonyMediaCounters)
    _outbound_queue: asyncio.Queue[bytes] = field(default_factory=asyncio.Queue)
    _outbound_task: asyncio.Task | None = None
    _closed: bool = False
    ws_connected_at: float | None = None
    first_outbound_pcm_at: float | None = None
    first_inbound_pcm_at: float | None = None
    _raw_inbound: bytearray = field(default_factory=bytearray)

    async def handle_ws(self, websocket: Any) -> None:
        """Attach mod_audio_stream (or lab client) WebSocket."""
        self.ws_connected_at = time.time()
        outbound_task = asyncio.create_task(self._pump_outbound_to_ws(websocket))
        try:
            while not self._closed:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                data = message.get("bytes")
                if not data:
                    continue
                if self.first_inbound_pcm_at is None:
                    self.first_inbound_pcm_at = time.time()
                self.counters.carrier_rx_frames += 1
                self.counters.carrier_rx_bytes += len(data)
                self.counters.gateway_rx_frames += 1
                self._raw_inbound.extend(data)
                frame = InboundMediaFrame(
                    pcm_s16le=data,
                    sample_rate=self.sample_rate,
                    track=StreamTrack.INBOUND,
                    call_id=self.call_id,
                    carrier_call_ref=self.fs_uuid,
                )
                await self.on_inbound(frame)
        finally:
            outbound_task.cancel()
            try:
                await outbound_task
            except asyncio.CancelledError:
                pass
            await self.close()

    async def enqueue_outbound_pcm(self, pcm: bytes) -> None:
        if self._closed:
            return
        await self._outbound_queue.put(pcm)

    async def _pump_outbound_to_ws(self, websocket: Any) -> None:
        try:
            while not self._closed:
                pcm = await self._outbound_queue.get()
                await websocket.send_bytes(pcm)
                self.counters.carrier_tx_frames += 1
                self.counters.carrier_tx_bytes += len(pcm)
                if self.first_outbound_pcm_at is None:
                    self.first_outbound_pcm_at = time.time()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("FS bridge outbound pump ended call_id=%s: %s", self.call_id, exc)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._outbound_task and not self._outbound_task.done():
            self._outbound_task.cancel()
            try:
                await self._outbound_task
            except asyncio.CancelledError:
                pass

    def raw_inbound_pcm(self) -> bytes:
        return bytes(self._raw_inbound)
