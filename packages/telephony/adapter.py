"""Telephony adapter contract — carrier media stream → CallActor ingress.

Asterisk (lab) and Telnyx (production candidate) implement the same boundary:
directional PCM in, TTS PCM out, per-call lifecycle + media counters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class StreamTrack(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


@dataclass(frozen=True)
class InboundMediaFrame:
    """One decoded uplink chunk from telephony adapter → AudioIngress."""

    pcm_s16le: bytes
    sample_rate: int
    track: StreamTrack = StreamTrack.INBOUND
    call_id: str = ""
    carrier_call_ref: str = ""


@dataclass
class TelephonyMediaCounters:
    """Carrier-side counters mirrored in trace (ADR-010 four-layer model)."""

    carrier_rx_frames: int = 0
    carrier_rx_bytes: int = 0
    carrier_tx_frames: int = 0
    carrier_tx_bytes: int = 0
    gateway_rx_frames: int = 0
    actor_rx_frames: int = 0

    def to_trace_dict(self) -> dict[str, int]:
        return {
            "carrier_rx_frames": self.carrier_rx_frames,
            "carrier_rx_bytes": self.carrier_rx_bytes,
            "carrier_tx_frames": self.carrier_tx_frames,
            "carrier_tx_bytes": self.carrier_tx_bytes,
            "gateway_rx_frames": self.gateway_rx_frames,
            "actor_rx_frames": self.actor_rx_frames,
        }


@runtime_checkable
class TelephonyAdapter(Protocol):
    """Per-call telephony boundary. Transport never owns dialogue."""

    async def open_call(
        self,
        call_id: str,
        *,
        family_id: str,
        elder_name: str,
        carrier_call_ref: str,
    ) -> None: ...

    async def push_inbound(self, frame: InboundMediaFrame) -> None: ...

    async def send_outbound_pcm(self, pcm_s16le: bytes, sample_rate: int) -> None: ...

    async def flush_outbound(self) -> None: ...

    async def hangup(self) -> None: ...

    def counters(self) -> TelephonyMediaCounters: ...
