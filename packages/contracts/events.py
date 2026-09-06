"""Durable event contract — record before side effect."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CallEvent(BaseModel):
    event_id: str
    call_id: str
    sequence_no: int
    occurred_at: datetime
    event_type: str
    schema_version: int = 1
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str

    model_config = {"frozen": True}


class EventTypes:
    CALL_STARTED = "CALL_STARTED"
    PERSON_ANSWERED = "PERSON_ANSWERED"
    CONSENT_CONFIRMED = "CONSENT_CONFIRMED"
    TURN_STARTED = "TURN_STARTED"
    STT_PARTIAL = "STT_PARTIAL"
    STT_FINAL = "STT_FINAL"
    RED_SIGNAL = "RED_SIGNAL"
    RED_SIGNAL_CONFIRMED = "RED_SIGNAL_CONFIRMED"
    RED_FALSE_ALARM = "RED_FALSE_ALARM"
    TTS_STARTED = "TTS_STARTED"
    TTS_INTERRUPTED = "TTS_INTERRUPTED"
    INCIDENT_REQUESTED = "INCIDENT_REQUESTED"
    CALL_ENDED = "CALL_ENDED"
    STATUS_ASSIGNED = "STATUS_ASSIGNED"
