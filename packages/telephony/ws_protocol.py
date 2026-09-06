"""Asterisk chan_websocket media control helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass

_FORMAT_SAMPLE_RATES: dict[str, int] = {
    "slin": 8000,
    "slin12": 12000,
    "slin16": 16000,
    "slin24": 24000,
    "slin32": 32000,
    "slin44": 44100,
    "slin48": 48000,
    "slin96": 96000,
    "slin192": 192000,
    "ulaw": 8000,
    "alaw": 8000,
}


@dataclass(frozen=True)
class MediaFormat:
    sample_rate: int
    frame_size_bytes: int
    encoding: str = "slin16"
    ptime_ms: int = 20


def _encoding_sample_rate(encoding: str, message: dict) -> int:
    if encoding in _FORMAT_SAMPLE_RATES:
        return _FORMAT_SAMPLE_RATES[encoding]
    if "sample_rate" in message:
        return int(message["sample_rate"])
    return 16000


def is_media_start(message: dict) -> bool:
    event = message.get("event") or message.get("type")
    return event == "MEDIA_START"


def parse_media_start(message: dict) -> MediaFormat:
    fmt = message.get("format")
    if isinstance(fmt, str):
        encoding = fmt
        sample_rate = _encoding_sample_rate(encoding, message)
    elif isinstance(fmt, dict):
        encoding = str(fmt.get("encoding") or fmt.get("format") or "slin16")
        sample_rate = int(fmt.get("sample_rate") or _encoding_sample_rate(encoding, message))
    else:
        encoding = "slin16"
        sample_rate = int(message.get("sample_rate") or 16000)

    ptime_ms = int(message.get("ptime") or 20)
    optimal = int(message.get("optimal_frame_size") or 0)
    if optimal <= 0:
        optimal = sample_rate * 2 * ptime_ms // 1000
    return MediaFormat(
        sample_rate=sample_rate,
        frame_size_bytes=optimal,
        encoding=encoding,
        ptime_ms=ptime_ms,
    )


def flush_media_command() -> str:
    return json.dumps({"command": "FLUSH_MEDIA"})


def is_control_message(raw: str) -> bool:
    return raw.strip().startswith("{")
