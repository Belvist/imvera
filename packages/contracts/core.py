"""Core integration contracts — observations, delivery stages, call results."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from packages.contracts.enums import FsmState, PublicCallStatus, RiskLevel


class DeliveryStage(StrEnum):
    """Product pipeline stage — never skip forward without evidence."""

    OBSERVATION_RECEIVED = "OBSERVATION_RECEIVED"
    PERSISTED = "PERSISTED"
    CORE_ACCEPTED = "CORE_ACCEPTED"
    APP_AVAILABLE = "APP_AVAILABLE"
    NOTIFICATION_DELIVERED = "NOTIFICATION_DELIVERED"
    NOTIFICATION_VIEWED = "NOTIFICATION_VIEWED"


class CallObservation(BaseModel):
    """One durable observation from a call — quote preserved."""

    observation_id: str
    call_id: str
    turn_id: int
    field: str | None = None
    value: str
    source_quote: str
    subject: str = "elder"
    negated: bool = False
    risk_level: RiskLevel = RiskLevel.NONE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    idempotency_key: str

    model_config = {"frozen": True}


class CallResultSnapshot(BaseModel):
    """Materialized call outcome for Core/app — candidate until CORE_ACCEPTED."""

    call_id: str
    family_id: str
    fsm_state: FsmState
    facts: dict[str, str] = Field(default_factory=dict)
    fact_quotes: dict[str, str] = Field(default_factory=dict)
    public_status: PublicCallStatus | None = None
    delivery_stage: DeliveryStage = DeliveryStage.OBSERVATION_RECEIVED
    observations: list[str] = Field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
