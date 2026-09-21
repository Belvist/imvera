"""FreeSWITCH PCM WebSocket bridge — directional READ/WRITE legs (ADR-013).

P0 validation may use mod_audio_stream (community uplink; bidirectional requires
commercial edition or future mod_imvera_audio). This module is transport-only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from packages.telephony.adapter import (
    InboundMediaFrame,
    OutboundAudioFrame,
    StreamTrack,
    TelephonyMediaCounters,
)
from packages.telephony.freeswitch_outbound import encode_stream_audio_json

log = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000
FRAME_MS = 20


class FreeSwitchOutboundMode(StrEnum):
    NONE = "none"
    RAW_BINARY = "raw_binary"
    STREAM_AUDIO_JSON = "stream_audio_json"


PushInboundFn = Callable[[InboundMediaFrame], Awaitable[None]]


@dataclass
class FreeSwitchBridgeSession:
    """One call UUID ↔ bidirectional PCM over WebSocket."""

    call_id: str
    fs_uuid: str
    on_inbound: PushInboundFn
    capture_sample_rate: int = TARGET_SAMPLE_RATE
    playback_sample_rate: int = TARGET_SAMPLE_RATE
    counters: TelephonyMediaCounters = field(default_factory=TelephonyMediaCounters)
    _outbound_queue: asyncio.Queue[OutboundAudioFrame] = field(default_factory=asyncio.Queue)
    _outbound_task: asyncio.Task | None = None
    uplink_only: bool = True
    outbound_mode: FreeSwitchOutboundMode = FreeSwitchOutboundMode.NONE
    _closed: bool = False
    ws_connected_at: float | None = None
    first_outbound_pcm_at: float | None = None
    first_inbound_pcm_at: float | None = None
    _raw_inbound: bytearray = field(default_factory=bytearray)
    # P0-B/C generation transport: cancelled set enforces drops at enqueue
    # AND send gates; per-generation counters prove 0 ghost frames.
    _cancelled_generations: set[str] = field(default_factory=set)
    _transport_epoch: int = 0
    _gen_enqueued: dict[str, int] = field(default_factory=dict)
    _gen_sent: dict[str, int] = field(default_factory=dict)
    _gen_dropped: dict[str, int] = field(default_factory=dict)
    _gen_cancel_at: dict[str, float] = field(default_factory=dict)
    _gen_send_race: dict[str, int] = field(default_factory=dict)

    def _duplex_enabled(self) -> bool:
        return not self.uplink_only or self.outbound_mode is not FreeSwitchOutboundMode.NONE

    async def handle_ws(self, websocket: Any) -> None:
        """Attach mod_audio_stream (or lab client) WebSocket."""
        self.ws_connected_at = time.time()
        outbound_task: asyncio.Task | None = None
        if self._duplex_enabled():
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
                if self.counters.gateway_rx_frames == 1:
                    log.info(
                        "FS bridge first uplink pcm call_id=%s bytes=%s",
                        self.call_id,
                        len(data),
                    )
                frame = InboundMediaFrame(
                    pcm_s16le=data,
                    sample_rate=self.capture_sample_rate,
                    track=StreamTrack.INBOUND,
                    call_id=self.call_id,
                    carrier_call_ref=self.fs_uuid,
                )
                await self.on_inbound(frame)
        finally:
            if outbound_task is not None:
                outbound_task.cancel()
                try:
                    await outbound_task
                except asyncio.CancelledError:
                    pass
            await self.close()

    async def enqueue_outbound_pcm(
        self,
        pcm: bytes,
        *,
        generation_id: str = "",
        phrase_id: str = "",
        sequence: int = 0,
        epoch: int = 0,
    ) -> bool:
        """Enqueue one typed downlink frame. Returns False when dropped
        (closed or generation cancelled) — never raises on cancel."""
        if self._closed:
            return False
        if generation_id and generation_id in self._cancelled_generations:
            self._gen_dropped[generation_id] = self._gen_dropped.get(generation_id, 0) + 1
            return False
        frame = OutboundAudioFrame(
            pcm_s16le=pcm,
            generation_id=generation_id,
            call_id=self.call_id,
            phrase_id=phrase_id,
            sequence=sequence,
            sample_rate=self.playback_sample_rate,
            epoch=epoch,
        )
        await self._outbound_queue.put(frame)
        if generation_id:
            self._gen_enqueued[generation_id] = self._gen_enqueued.get(generation_id, 0) + 1
        return True

    def cancel_generation(self, generation_id: str) -> dict[str, Any]:
        """Addressable cancel (never global): purge queued frames of exactly
        this generation, reject future enqueues. Idempotent. Returns the
        LOCAL_PURGE_ACK payload — local only, see request_downstream_stop
        for the separate downstream measurement."""
        now = time.time()
        already = generation_id in self._cancelled_generations
        self._cancelled_generations.add(generation_id)
        self._transport_epoch += 1
        purged_frames = 0
        purged_bytes = 0
        kept: list[OutboundAudioFrame] = []
        while True:
            try:
                frame = self._outbound_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if frame.generation_id == generation_id:
                purged_frames += 1
                purged_bytes += len(frame.pcm_s16le)
            else:
                kept.append(frame)
        for frame in kept:
            self._outbound_queue.put_nowait(frame)
        if generation_id not in self._gen_cancel_at:
            self._gen_cancel_at[generation_id] = now
        return {
            "generation_id": generation_id,
            "purged_frames": purged_frames,
            "purged_bytes": purged_bytes,
            "already_cancelled": already,
            "transport_epoch": self._transport_epoch,
            "local_purge_ack_at": now,
        }

    def generation_report(self, generation_id: str) -> dict[str, Any]:
        return {
            "generation_id": generation_id,
            "enqueued": self._gen_enqueued.get(generation_id, 0),
            "sent": self._gen_sent.get(generation_id, 0),
            "dropped": self._gen_dropped.get(generation_id, 0),
            "sent_race": self._gen_send_race.get(generation_id, 0),
            "cancelled": generation_id in self._cancelled_generations,
            "cancel_requested_at": self._gen_cancel_at.get(generation_id),
        }

    async def request_downstream_stop(self) -> dict[str, Any]:
        """Best-effort downstream playback stop that MUST NOT close the media WS.

        Sends ``uuid_audio_stream <uuid> break`` (clears the FS-side playback
        queue; forward/uplink streaming continues) — NEVER ``... stop``, which
        STOPS THE AUDIO STREAM AND CLOSES the WebSocket carrying this
        CallActor session (a barge-in would then kill every later generation).

        Evidence for ``break`` (running imvera-freeswitch, FS 1.10.12):
        ``break`` verb + ``break_audio_queue`` / ``AudioProcessor::breakAudio``
        symbols in mod_audio_stream.so; upstream v1.0.3 notes "drain mode
        added to break api method". ``pause`` is NOT a substitute (it gates
        the uplink/caller stream, not downlink playback); core ``uuid_break``
        targets dialplan apps, not media-bug playback. Live audible effect is
        NOT verified here — see the ack contract below.

        Returns requested_at/result — a transport measurement, NEVER an
        audible-silence claim. ``acked_at`` is None on failure and ``result``
        holds the raw ESL reply (e.g. "-ERR ..." when unsupported); the call
        never raises and never closes the session. Local cancel
        (cancel_generation/LOCAL_PURGE_ACK) is the guaranteed path and is
        unaffected by this call's outcome.
        """
        from packages.telephony.freeswitch_esl import freeswitch_api

        requested_at = time.time()
        try:
            result = await freeswitch_api(f"uuid_audio_stream {self.fs_uuid} break")
            return {
                "requested_at": requested_at,
                "acked_at": time.time(),
                "command": "uuid_audio_stream break",
                "result": str(result)[:200],
            }
        except Exception as exc:
            return {
                "requested_at": requested_at,
                "acked_at": None,
                "command": "uuid_audio_stream break",
                "error": str(exc)[:200],
            }

    async def _pump_outbound_to_ws(self, websocket: Any) -> None:
        try:
            while not self._closed:
                frame = await self._outbound_queue.get()
                # Send gate: a frame extracted before cancel must still drop.
                if frame.generation_id and frame.generation_id in self._cancelled_generations:
                    self._gen_dropped[frame.generation_id] = (
                        self._gen_dropped.get(frame.generation_id, 0) + 1
                    )
                    continue
                pcm = frame.pcm_s16le
                send_started_cancelled = bool(
                    frame.generation_id
                    and frame.generation_id in self._cancelled_generations
                )
                if self.outbound_mode is FreeSwitchOutboundMode.STREAM_AUDIO_JSON:
                    message = encode_stream_audio_json(pcm, self.playback_sample_rate)
                    await websocket.send_text(message)
                    tx_bytes = len(message.encode("utf-8"))
                else:
                    await websocket.send_bytes(pcm)
                    tx_bytes = len(pcm)
                # Race accounting: cancel landed DURING the send await (after
                # the gate). Bytes are already handed to the socket — this is
                # why LOCAL_PURGE_ACK never claims audible silence; only the
                # measured downstream stop does. Bounded to in-flight frames.
                if (
                    frame.generation_id
                    and not send_started_cancelled
                    and frame.generation_id in self._cancelled_generations
                ):
                    self._gen_send_race[frame.generation_id] = (
                        self._gen_send_race.get(frame.generation_id, 0) + 1
                    )
                self.counters.carrier_tx_frames += 1
                self.counters.carrier_tx_bytes += tx_bytes
                if frame.generation_id:
                    self._gen_sent[frame.generation_id] = (
                        self._gen_sent.get(frame.generation_id, 0) + 1
                    )
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
