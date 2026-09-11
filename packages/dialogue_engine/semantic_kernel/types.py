"""Canonical semantic types for Turn Semantic Kernel."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class SpanType(StrEnum):
    ISSUE = "ISSUE"
    BODY_SITE = "BODY_SITE"
    TIME = "TIME"
    DURATION = "DURATION"
    SEVERITY = "SEVERITY"
    STATUS = "STATUS"
    MEDICATION = "MEDICATION"
    PERSON = "PERSON"
    ACTIVITY = "ACTIVITY"
    NEGATION = "NEGATION"
    UNCERTAINTY = "UNCERTAINTY"


class RelationType(StrEnum):
    BODY_OF = "BODY_OF"
    ONSET_OF = "ONSET_OF"
    DURATION_OF = "DURATION_OF"
    SEVERITY_OF = "SEVERITY_OF"
    STATUS_OF = "STATUS_OF"
    SUBJECT_OF = "SUBJECT_OF"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    NEGATES = "NEGATES"
    CORRECTS = "CORRECTS"
    REFERS_TO = "REFERS_TO"


class SubjectKind(StrEnum):
    SPEAKER = "speaker"
    OTHER_PERSON = "other_person"
    UNKNOWN = "unknown"


ObservationStatus = Literal["candidate", "confirmed", "superseded", "rejected"]


class SemanticSpan(BaseModel):
    span_id: str
    type: SpanType
    text: str
    start: int
    end: int
    normalized: str = ""
    confidence: float = 1.0

    model_config = {"frozen": True}


class SemanticRelation(BaseModel):
    type: RelationType
    source_span_id: str
    target_span_id: str
    confidence: float = 1.0

    model_config = {"frozen": True}


class TemporalFrame(BaseModel):
    current: bool | None = None
    onset: str | None = None
    duration: str | None = None
    recurrence: str | None = None
    raw_evidence: str = ""

    model_config = {"frozen": True}


class CorrectionRecord(BaseModel):
    target: str
    old_evidence: str | None = None
    new_evidence: str
    span_id: str | None = None

    model_config = {"frozen": True}


class Observation(BaseModel):
    observation_id: str
    episode_id: str | None = None
    attribute: str
    value: str
    normalized_value: str = ""
    body_site: str | None = None
    issue_normalized: str = ""
    goal_id: str | None = None
    subject: SubjectKind = SubjectKind.SPEAKER
    temporal: TemporalFrame = Field(default_factory=TemporalFrame)
    confidence: float = 1.0
    source_turn_id: str = ""
    evidence: str = ""
    status: ObservationStatus = "candidate"

    model_config = {"frozen": False}


class SemanticKernelResult(BaseModel):
    raw_text: str
    utterance_id: str
    dialogue_act: str = "answer"
    control: str = "none"
    spans: tuple[SemanticSpan, ...] = ()
    relations: tuple[SemanticRelation, ...] = ()
    observations: tuple[Observation, ...] = ()
    user_question: str | None = None
    corrections: tuple[CorrectionRecord, ...] = ()
    confidence: float = 1.0
    ambiguity: tuple[str, ...] = ()
    level: int = 1
    fallback_used: bool = False
    elapsed_ms: float = 0.0
    route: str = "kernel_l1"

    model_config = {"frozen": True}
