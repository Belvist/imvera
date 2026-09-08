"""Telnyx media stream session — bidirectional WS adapter to CallActor."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from packages.telephony.telnyx_codec import (
    TARGET_SAMPLE_RATE,
    TelnyxNegotiatedFormat,
    decode_inbound_payload,
    encode_outbound_b64,
)
from packages.telephony.telnyx_reorder import TelnyxMediaReorderBuffer, TelnyxReorderCounters
from packages.voice_runtime.audio import pcm_rms_s16le

log = logging.getLogger(__name__)

EmitStageFn = Callable[[str, dict[str, Any]], Awaitable[None]]
PushPcmFn = Callable[[bytes, int], Awaitable[None]]
SendWsTextFn = Callable[[str], Awaitable[None]]
NoteTransportFn = Callable[[int, float], None]


@dataclass
class TelnyxStreamKeys:
    stream_id: str
    call_control_id: str
    call_session_id: str


@dataclass
class TelnyxMediaSession:
    """One Telnyx WebSocket media stream ↔ one CallActor."""

    call_id: str
    keys: TelnyxStreamKeys
    fmt: TelnyxNegotiatedFormat
    push_pcm: PushPcmFn
    send_ws_text: SendWsTextFn
    emit_stage: EmitStageFn
    note_transport: NoteTransportFn | None = None
    reorder: TelnyxMediaReorderBuffer = field(default_factory=TelnyxMediaReorderBuffer)
    _outbound_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _stopped: bool = False
    _outbound_generation: int = 0
    _actor_pcm_bytes: int = 0

    @property
    def reorder_counters(self) -> TelnyxReorderCounters:
        return self.reorder.counters

    async def handle_connected(self, version: str = "") -> None:
        await self.emit_stage("telnyx.connected", version=version)

    async def handle_start(self, start_payload: dict[str, Any], stream_id: str) -> None:
        media_format = start_payload.get("media_format") or {}
        await self.emit_stage(
            "telnyx.start",
            stream_id=stream_id,
            call_control_id=self.keys.call_control_id,
            call_session_id=self.keys.call_session_id,
            encoding=str(media_format.get("encoding", self.fmt.encoding.value)),
            sample_rate=self.fmt.sample_rate,
            channels=self.fmt.channels,
        )

    async def handle_media(
        self,
        *,
        track: str,
        chunk: str | int | None,
        payload_b64: str,
        timestamp: str | None = None,
    ) -> None:
        track_norm = (track or "").strip().lower()
        if track_norm in {"outbound", "out"}:
            await self.emit_stage(
                "telnyx.protocol_anomaly",
                reason="outbound_track_on_inbound_stream",
                track=track,
            )
            return
        if not payload_b64:
            return
        chunk_id = int(chunk) if chunk is not None else 0
        ordered = self.reorder.push(chunk_id, payload_b64)
        gaps_before = self.reorder.counters.telnyx_media_gaps
        for ord_chunk, b64 in ordered:
            pcm = decode_inbound_payload(b64, self.fmt, target_sample_rate=TARGET_SAMPLE_RATE)
            rms = round(pcm_rms_s16le(pcm), 1) if pcm else 0.0
            peak = 0
            if len(pcm) >= 2:
                peak = max(
                    abs(int.from_bytes(pcm[i : i + 2], "little", signed=True))
                    for i in range(0, len(pcm) - 1, 2)
                )
            if self.note_transport is not None:
                self.note_transport(len(pcm), rms)
            await self.emit_stage(
                "telnyx.media",
                track="inbound",
                chunk=ord_chunk,
                timestamp=timestamp or "",
                encoded_bytes=len(b64),
                decoded_pcm_bytes=len(pcm),
                rms=rms,
                peak=peak,
            )
            self._actor_pcm_bytes += len(pcm)
            await self.push_pcm(pcm, TARGET_SAMPLE_RATE)
        if self.reorder.counters.telnyx_media_gaps > gaps_before:
            await self.emit_stage(
                "telnyx.gap",
                chunk=chunk_id,
                expected=gaps_before,
                gaps=self.reorder.counters.telnyx_media_gaps,
            )

    async def handle_dtmf(self, digit: str) -> None:
        await self.emit_stage("telnyx.dtmf", digit=digit)

    async def handle_mark(self, name: str) -> None:
        await self.emit_stage("telnyx.mark", name=name)

    async def handle_error(self, code: int, title: str, detail: str) -> None:
        await self.emit_stage("telnyx.error", code=code, title=title, detail=detail)

    async def handle_stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        await self.emit_stage("telnyx.stop", stream_id=self.keys.stream_id)

    async def send_outbound_pcm(self, pcm16le: bytes, source_sample_rate: int) -> None:
        if self._stopped or not pcm16le:
            return
        send_gen = self._outbound_generation
        payload_b64 = encode_outbound_b64(pcm16le, source_sample_rate, self.fmt)
        msg = json.dumps({"event": "media", "media": {"payload": payload_b64}})
        async with self._outbound_lock:
            if send_gen != self._outbound_generation:
                return
            await self.send_ws_text(msg)

    async def send_clear(self) -> None:
        async with self._outbound_lock:
            self._outbound_generation += 1
            await self.send_ws_text(json.dumps({"event": "clear"}))
            await self.emit_stage("telnyx.clear", generation=self._outbound_generation)

    async def send_mark(self, name: str) -> None:
        async with self._outbound_lock:
            await self.send_ws_text(
                json.dumps({"event": "mark", "mark": {"name": name}})
            )
            await self.emit_stage("telnyx.mark", name=name, outbound=True)

    def pipeline_trace(self) -> dict[str, int]:
        rc = self.reorder.counters
        return {
            "transport_rx_frames": rc.telnyx_media_received,
            "transport_rx_bytes": rc.telnyx_payload_bytes,
            "actor_pcm_bytes": self._actor_pcm_bytes,
            **rc.to_trace_dict(),
        }


def new_telnyx_call_id(call_control_id: str) -> str:
    digest = uuid.uuid5(uuid.NAMESPACE_URL, call_control_id).hex[:10]
    return f"telnyx-{digest}"


def parse_stream_keys(start_payload: dict[str, Any], stream_id: str) -> TelnyxStreamKeys:
    return TelnyxStreamKeys(
        stream_id=stream_id,
        call_control_id=str(start_payload.get("call_control_id", "")),
        call_session_id=str(start_payload.get("call_session_id", "")),
    )
