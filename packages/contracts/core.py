"""Core persistence contracts."""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from packages.contracts.enums import FsmState, PublicCallStatus, RiskLevel

if TYPE_CHECKING:
    from packages.contracts.events import CallEvent


class DeliveryStage(StrEnum):
    OBSERVATION_RECEIVED = "OBSERVATION_RECEIVED"
    PERSISTED = "PERSISTED"
    CORE_ACCEPTED = "CORE_ACCEPTED"
    APP_AVAILABLE = "APP_AVAILABLE"
    NOTIFICATION_DELIVERED = "NOTIFICATION_DELIVERED"
    NOTIFICATION_VIEWED = "NOTIFICATION_VIEWED"


class TerminationReason(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    UNRESOLVED = "UNRESOLVED"
    CONSENT_DECLINED = "CONSENT_DECLINED"
    CONSENT_REVOKED = "CONSENT_REVOKED"
    DEFERRED = "DEFERRED"
    WRONG_PERSON = "WRONG_PERSON"
    EARLY_GOODBYE = "EARLY_GOODBYE"
    DISCONNECTED = "DISCONNECTED"
    RISK_ESCALATION = "RISK_ESCALATION"


class CallObservation(BaseModel):
    observation_id: str
    call_id: str
    turn_id: int
    field: str | None = None
    value: str
    source_quote: str
    subject: str = "elder"
    negated: bool = False
    risk_level: RiskLevel = RiskLevel.NONE
    episode_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    idempotency_key: str

    model_config = {"frozen": True}


class CallResultSnapshot(BaseModel):
    call_id: str
    family_id: str
    fsm_state: FsmState
    facts: dict[str, str] = Field(default_factory=dict)
    fact_quotes: dict[str, str] = Field(default_factory=dict)
    public_status: PublicCallStatus | None = None
    delivery_stage: DeliveryStage = DeliveryStage.OBSERVATION_RECEIVED
    observations: list[str] = Field(default_factory=list)
    partial: bool = True
    call_ended: bool = False
    termination_reason: TerminationReason | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PersistResult(BaseModel):
    ok: bool
    delivery_stage: DeliveryStage
    error: str | None = None


class CallRecordStore(ABC):
    @abstractmethod
    def ensure_call(self, call_id: str, family_id: str) -> PersistResult: ...

    @abstractmethod
    def append_event(self, event: "CallEvent", family_id: str) -> PersistResult: ...

    @abstractmethod
    def save_observation(
        self,
        observation: CallObservation,
        family_id: str,
    ) -> PersistResult: ...

    @abstractmethod
    def finalize_call(self, snapshot: CallResultSnapshot) -> PersistResult: ...

    @abstractmethod
    def get_call_result(self, call_id: str, family_id: str) -> CallResultSnapshot | None: ...

    @abstractmethod
    def get_events(self, call_id: str, family_id: str) -> list: ...

    @abstractmethod
    def save_dialogue_snapshot(
        self,
        snapshot: CallResultSnapshot,
        family_id: str,
    ) -> PersistResult: ...
