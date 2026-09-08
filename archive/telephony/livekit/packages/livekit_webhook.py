"""LiveKit webhook verification and event parsing."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class LiveKitWebhookEvent:
    event: str
    room_name: str
    room_sid: str
    participant_identity: str
    participant_sid: str
    participant_kind: int
    track_sid: str
    raw: dict[str, Any]


def verify_and_parse_webhook(
    body: bytes,
    auth_header: str,
    api_key: str,
    api_secret: str,
) -> LiveKitWebhookEvent:
    from livekit.api import TokenVerifier, WebhookReceiver

    receiver = WebhookReceiver(TokenVerifier(api_key, api_secret))
    text = body.decode("utf-8")
    event = receiver.receive(text, auth_header)
    payload = json.loads(text) if text.strip().startswith("{") else {}
    room = event.room
    participant = event.participant
    track = event.track
    return LiveKitWebhookEvent(
        event=str(event.event),
        room_name=room.name if room else "",
        room_sid=room.sid if room else "",
        participant_identity=participant.identity if participant else "",
        participant_sid=participant.sid if participant else "",
        participant_kind=int(participant.kind) if participant else 0,
        track_sid=track.sid if track else "",
        raw=payload,
    )
