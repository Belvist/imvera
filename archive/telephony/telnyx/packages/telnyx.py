"""Telnyx Programmable Voice — media streaming WebSocket adapter.

Parses Telnyx WS JSON (connected / start / media / stop / mark / dtmf / error).
Production path per ADR-011. Requires Telnyx account + stream URL.

Docs: https://developers.telnyx.com/docs/voice/programmable-voice/media-streaming
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from packages.telephony.adapter import InboundMediaFrame, StreamTrack

log = logging.getLogger(__name__)

_TELNYX_CODEC_SAMPLE_RATES: dict[str, int] = {
    "PCMU": 8000,
    "PCMA": 8000,
    "G722": 8000,
    "OPUS": 16000,
    "AMR-WB": 16000,
    "L16": 16000,
}


class TelnyxStreamEventKind(StrEnum):
    CONNECTED = "connected"
    START = "start"
    MEDIA = "media"
    STOP = "stop"
    MARK = "mark"
    DTMF = "dtmf"
    ERROR = "error"
    CLEAR = "clear"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TelnyxMediaFormat:
    encoding: str
    sample_rate: int
    channels: int = 1


@dataclass(frozen=True)
class TelnyxStreamStart:
    call_control_id: str
    call_session_id: str
    stream_id: str
    media_format: TelnyxMediaFormat
    from_number: str = ""
    to_number: str = ""


@dataclass(frozen=True)
class TelnyxStreamMedia:
    track: StreamTrack
    payload_pcm: bytes
    sample_rate: int
    encoding: str
    stream_id: str
    sequence_number: int | None = None
    chunk: str | None = None


@dataclass(frozen=True)
class TelnyxStreamEvent:
    kind: TelnyxStreamEventKind
    start: TelnyxStreamStart | None = None
    media: TelnyxStreamMedia | None = None
    raw: dict[str, Any] | None = None


def _parse_track(raw: str) -> StreamTrack:
    normalized = (raw or "").strip().lower()
    if normalized in {"outbound", "out"}:
        return StreamTrack.OUTBOUND
    return StreamTrack.INBOUND


def _payload_to_pcm(payload_b64: str, encoding: str, sample_rate: int) -> bytes:
    """Decode Telnyx media payload to PCM16 mono for CallActor ingress.

    Telnyx sends base64 RTP payload (no headers). For L16/PCMU lab spike we
    decode to bytes; gateway resamples to 16 kHz before Silero/GigaAM.
    """
    raw = base64.b64decode(payload_b64, validate=False)
    enc = encoding.upper()
    if enc == "L16":
        return raw
    if enc in {"PCMU", "ULAW"}:
        import audioop

        return audioop.ulaw2lin(raw, 2)
    if enc in {"PCMA", "ALAW"}:
        import audioop

        return audioop.alaw2lin(raw, 2)
    log.warning("Telnyx encoding %s not decoded — passing raw (%d bytes)", enc, len(raw))
    return raw


def parse_telnyx_ws_message(
    raw: str | bytes,
    *,
    default_encoding: str = "PCMU",
    default_sample_rate: int = 8000,
) -> TelnyxStreamEvent:
    """Parse one Telnyx media-stream WebSocket JSON message."""
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace")
    else:
        text = raw
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return TelnyxStreamEvent(kind=TelnyxStreamEventKind.UNKNOWN, raw=None)

    if not isinstance(data, dict):
        return TelnyxStreamEvent(kind=TelnyxStreamEventKind.UNKNOWN, raw=data)

    event = str(data.get("event", "")).lower()
    if event == "connected":
        return TelnyxStreamEvent(kind=TelnyxStreamEventKind.CONNECTED, raw=data)

    if event == "start":
        start = data.get("start") or {}
        fmt = start.get("media_format") or {}
        encoding = str(fmt.get("encoding", default_encoding))
        sample_rate = int(fmt.get("sample_rate", _TELNYX_CODEC_SAMPLE_RATES.get(encoding, default_sample_rate)))
        media_format = TelnyxMediaFormat(
            encoding=encoding,
            sample_rate=sample_rate,
            channels=int(fmt.get("channels", 1)),
        )
        return TelnyxStreamEvent(
            kind=TelnyxStreamEventKind.START,
            start=TelnyxStreamStart(
                call_control_id=str(start.get("call_control_id", "")),
                call_session_id=str(start.get("call_session_id", "")),
                stream_id=str(data.get("stream_id", "")),
                media_format=media_format,
                from_number=str(start.get("from", "")),
                to_number=str(start.get("to", "")),
            ),
            raw=data,
        )

    if event == "media":
        media = data.get("media") or {}
        track = _parse_track(str(media.get("track", "inbound")))
        payload = str(media.get("payload", ""))
        encoding = default_encoding
        sample_rate = default_sample_rate
        stream_id = str(data.get("stream_id", ""))
        seq_raw = data.get("sequence_number")
        sequence_number = int(seq_raw) if seq_raw is not None else None
        pcm = _payload_to_pcm(payload, encoding, sample_rate) if payload else b""
        return TelnyxStreamEvent(
            kind=TelnyxStreamEventKind.MEDIA,
            media=TelnyxStreamMedia(
                track=track,
                payload_pcm=pcm,
                sample_rate=sample_rate,
                encoding=encoding,
                stream_id=stream_id,
                sequence_number=sequence_number,
                chunk=str(media.get("chunk")) if media.get("chunk") is not None else None,
            ),
            raw=data,
        )

    if event == "stop":
        return TelnyxStreamEvent(kind=TelnyxStreamEventKind.STOP, raw=data)

    if event == "mark":
        return TelnyxStreamEvent(kind=TelnyxStreamEventKind.MARK, raw=data)

    if event == "dtmf":
        return TelnyxStreamEvent(kind=TelnyxStreamEventKind.DTMF, raw=data)

    if event == "error":
        return TelnyxStreamEvent(kind=TelnyxStreamEventKind.ERROR, raw=data)

    if event == "clear":
        return TelnyxStreamEvent(kind=TelnyxStreamEventKind.CLEAR, raw=data)

    return TelnyxStreamEvent(kind=TelnyxStreamEventKind.UNKNOWN, raw=data)


def telnyx_media_to_ingress(
    event: TelnyxStreamEvent,
    *,
    call_id: str,
    media_format: TelnyxMediaFormat | None = None,
) -> InboundMediaFrame | None:
    """Map Telnyx MEDIA(inbound) → InboundMediaFrame. Outbound track ignored."""
    if event.kind != TelnyxStreamEventKind.MEDIA or event.media is None:
        return None
    media = event.media
    if media.track != StreamTrack.INBOUND:
        return None
    if not media.payload_pcm:
        return None
    fmt = media_format
    sample_rate = fmt.sample_rate if fmt else media.sample_rate
    return InboundMediaFrame(
        pcm_s16le=media.payload_pcm,
        sample_rate=sample_rate,
        track=StreamTrack.INBOUND,
        call_id=call_id,
        carrier_call_ref=media.stream_id,
    )


def encode_outbound_rtp_payload(pcm_s16le: bytes, *, encoding: str = "PCMU") -> str:
    """Encode PCM for Telnyx bidirectional media WS (RTP payload, base64)."""
    enc = encoding.upper()
    if enc == "L16":
        payload = pcm_s16le
    elif enc in {"PCMU", "ULAW"}:
        import audioop

        payload = audioop.lin2ulaw(pcm_s16le, 2)
    elif enc in {"PCMA", "ALAW"}:
        import audioop

        payload = audioop.lin2alaw(pcm_s16le, 2)
    else:
        raise ValueError(f"Unsupported Telnyx outbound encoding: {encoding}")
    return base64.b64encode(payload).decode("ascii")


def outbound_media_message(payload_b64: str) -> dict[str, Any]:
    return {"event": "media", "media": {"payload": payload_b64}}


def clear_media_message() -> dict[str, str]:
    return {"event": "clear"}
