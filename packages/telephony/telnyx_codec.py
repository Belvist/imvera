"""Telnyx media codec — PCMU fallback, L16/16kHz production preferred (ADR-011)."""

from __future__ import annotations

import audioop
import base64
import struct
from dataclasses import dataclass
from enum import StrEnum

TARGET_SAMPLE_RATE = 16000


class TelnyxCodecError(ValueError):
    """Unsupported or invalid Telnyx media_format."""


class TelnyxEncoding(StrEnum):
    PCMU = "PCMU"
    PCMA = "PCMA"
    L16 = "L16"


@dataclass(frozen=True)
class TelnyxNegotiatedFormat:
    encoding: TelnyxEncoding
    sample_rate: int
    channels: int = 1

    @classmethod
    def from_start(cls, media_format: dict) -> TelnyxNegotiatedFormat:
        encoding_raw = str(media_format.get("encoding", "")).strip().upper()
        if encoding_raw in {"ULAW", "MU-LAW"}:
            encoding_raw = "PCMU"
        if encoding_raw in {"ALAW", "A-LAW"}:
            encoding_raw = "PCMA"
        try:
            encoding = TelnyxEncoding(encoding_raw)
        except ValueError:
            raise TelnyxCodecError(f"unsupported encoding: {encoding_raw!r}") from None
        sample_rate = int(media_format.get("sample_rate", 0))
        channels = int(media_format.get("channels", 1))
        if sample_rate <= 0 or channels != 1:
            raise TelnyxCodecError(
                f"unsupported media_format: encoding={encoding_raw} "
                f"sample_rate={sample_rate} channels={channels}"
            )
        if encoding == TelnyxEncoding.PCMU and sample_rate != 8000:
            raise TelnyxCodecError(f"PCMU requires 8000 Hz, got {sample_rate}")
        if encoding == TelnyxEncoding.PCMA and sample_rate != 8000:
            raise TelnyxCodecError(f"PCMA requires 8000 Hz, got {sample_rate}")
        if encoding == TelnyxEncoding.L16 and sample_rate not in {8000, 16000}:
            raise TelnyxCodecError(f"L16 requires 8000 or 16000 Hz, got {sample_rate}")
        return cls(encoding=encoding, sample_rate=sample_rate, channels=channels)


def _resample_to_16k(pcm16le: bytes, source_rate: int) -> bytes:
    if source_rate == TARGET_SAMPLE_RATE:
        return pcm16le
    converted, _ = audioop.ratecv(pcm16le, 2, 1, source_rate, TARGET_SAMPLE_RATE, None)
    return converted


def _l16_be_to_pcm16le(payload: bytes) -> bytes:
    n = len(payload) - (len(payload) % 2)
    if n <= 0:
        return b""
    count = n // 2
    samples = struct.unpack(f">{count}h", payload[:n])
    return struct.pack(f"<{count}h", *samples)


def _pcm16le_to_l16_be(pcm16le: bytes) -> bytes:
    n = len(pcm16le) - (len(pcm16le) % 2)
    if n <= 0:
        return b""
    count = n // 2
    samples = struct.unpack(f"<{count}h", pcm16le[:n])
    return struct.pack(f">{count}h", *samples)


def decode_inbound_payload(
    payload_b64: str,
    fmt: TelnyxNegotiatedFormat,
    *,
    target_sample_rate: int = TARGET_SAMPLE_RATE,
) -> bytes:
    """Decode Telnyx RTP payload (base64) → PCM16LE @ target_sample_rate."""
    if not payload_b64:
        return b""
    raw = base64.b64decode(payload_b64, validate=False)
    if fmt.encoding == TelnyxEncoding.L16:
        pcm = _l16_be_to_pcm16le(raw)
    elif fmt.encoding == TelnyxEncoding.PCMU:
        pcm = audioop.ulaw2lin(raw, 2)
    else:
        pcm = audioop.alaw2lin(raw, 2)
    return _resample_to_16k(pcm, fmt.sample_rate) if fmt.sample_rate != target_sample_rate else pcm


def encode_outbound_payload(
    pcm16le: bytes,
    source_sample_rate: int,
    fmt: TelnyxNegotiatedFormat,
) -> bytes:
    """Encode PCM16LE (CallActor output) → Telnyx RTP payload bytes."""
    pcm = pcm16le
    if source_sample_rate != fmt.sample_rate:
        pcm, _ = audioop.ratecv(pcm16le, 2, 1, source_sample_rate, fmt.sample_rate, None)
    if fmt.encoding == TelnyxEncoding.L16:
        return _pcm16le_to_l16_be(pcm)
    if fmt.encoding == TelnyxEncoding.PCMU:
        return audioop.lin2ulaw(pcm, 2)
    return audioop.lin2alaw(pcm, 2)


def encode_outbound_b64(
    pcm16le: bytes,
    source_sample_rate: int,
    fmt: TelnyxNegotiatedFormat,
) -> str:
    return base64.b64encode(
        encode_outbound_payload(pcm16le, source_sample_rate, fmt)
    ).decode("ascii")
