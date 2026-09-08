"""Telnyx WebSocket message router — testable without FastAPI."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from packages.telephony.telnyx_adapter import TelnyxMediaSession
from packages.telephony.telnyx_codec import TelnyxCodecError, TelnyxNegotiatedFormat

log = logging.getLogger(__name__)


class TelnyxWsCloseReason(StrEnum):
    UNSUPPORTED_MEDIA = "unsupported_media"
    PROTOCOL_ERROR = "protocol_error"
    SESSION_STOPPED = "session_stopped"


@dataclass
class TelnyxWsRouter:
    """Route Telnyx WS JSON events to TelnyxMediaSession."""

    session: TelnyxMediaSession | None = None
    _started: bool = False
    close_reason: TelnyxWsCloseReason | None = None
    close_detail: str = ""

    async def handle_text(self, raw: str) -> bool:
        """Return False when the WebSocket should close."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self.close_reason = TelnyxWsCloseReason.PROTOCOL_ERROR
            self.close_detail = "invalid_json"
            return False
        if not isinstance(data, dict):
            self.close_reason = TelnyxWsCloseReason.PROTOCOL_ERROR
            self.close_detail = "not_object"
            return False
        return await self.handle_event(data)

    async def handle_event(self, data: dict[str, Any]) -> bool:
        event = str(data.get("event", "")).lower()
        if event == "connected":
            version = str(data.get("version", ""))
            if self.session is not None:
                await self.session.handle_connected(version)
            return True

        if event == "start":
            if self._started:
                return True
            start = data.get("start") or {}
            stream_id = str(data.get("stream_id", ""))
            media_format = start.get("media_format") or {}
            try:
                TelnyxNegotiatedFormat.from_start(media_format)
            except TelnyxCodecError as exc:
                if self.session is not None:
                    await self.session.emit_stage(
                        "telnyx.unsupported_media",
                        media_format=media_format,
                        error=str(exc),
                    )
                self.close_reason = TelnyxWsCloseReason.UNSUPPORTED_MEDIA
                self.close_detail = str(exc)
                return False
            if self.session is not None:
                await self.session.handle_start(start, stream_id)
            self._started = True
            return True

        if self.session is None or not self._started:
            self.close_reason = TelnyxWsCloseReason.PROTOCOL_ERROR
            self.close_detail = "media_before_start"
            return False

        if event == "media":
            media = data.get("media") or {}
            await self.session.handle_media(
                track=str(media.get("track", "inbound")),
                chunk=media.get("chunk"),
                payload_b64=str(media.get("payload", "")),
                timestamp=str(data.get("timestamp", media.get("timestamp", ""))),
            )
            return True

        if event == "dtmf":
            dtmf = data.get("dtmf") or {}
            digit = str(dtmf.get("digit", ""))
            await self.session.handle_dtmf(digit)
            return True

        if event == "mark":
            mark = data.get("mark") or {}
            await self.session.handle_mark(str(mark.get("name", "")))
            return True

        if event == "error":
            err = data.get("payload") or data.get("error") or {}
            await self.session.handle_error(
                int(err.get("code", 0)),
                str(err.get("title", "")),
                str(err.get("detail", "")),
            )
            return True

        if event == "stop":
            await self.session.handle_stop()
            self.close_reason = TelnyxWsCloseReason.SESSION_STOPPED
            return False

        log.debug("Telnyx WS ignored event=%s", event)
        return True
