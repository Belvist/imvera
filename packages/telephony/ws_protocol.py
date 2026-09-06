"""Asterisk chan_websocket media control helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class MediaFormat:
    sample_rate: int
    frame_size_bytes: int
    encoding: str = "slin16"


def parse_media_start(message: dict) -> MediaFormat:
    fmt = message.get("format") or {}
    sample_rate = int(fmt.get("sample_rate") or message.get("sample_rate") or 16000)
    optimal = int(message.get("optimal_frame_size") or message.get("frame_size") or 320)
    encoding = str(fmt.get("encoding") or fmt.get("format") or "slin16")
    return MediaFormat(sample_rate=sample_rate, frame_size_bytes=optimal, encoding=encoding)


def flush_media_command() -> str:
    return json.dumps({"type": "FLUSH_MEDIA"})


def is_control_message(raw: str) -> bool:
    return raw.strip().startswith("{")
