"""Production semantic contract — ADR-008 §5.

Legacy TurnInterpretation in this package remains for text-path tests during migration.
Voice runtime uses SemanticPayload + TurnContext.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

# Re-export legacy types for existing imports
from packages.contracts.interpretation import FactCandidate as LegacyFactCandidate
from packages.contracts.interpretation import TurnInterpretation as LegacyTurnInterpretation

__all__ = [
    "ConfirmedFact",
    "Evidence",
    "FactCandidate",
    "InterpretationProvider",
    "LegacyFactCandidate",
    "LegacyTurnInterpretation",
    "RiskCandidate",
    "RiskEpisodeContext",
    "SemanticPayload",
    "TurnContext",
    "TurnInterpretation",
    "evidence_matches",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Evidence(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)


class FactCandidate(StrictModel):
    field: Literal["wellness", "mood", "sleep", "plans"]
    value: str = Field(min_length=1, max_length=500)
    subject: Literal["speaker", "other", "unknown"]
    temporal_scope: Literal["now", "today", "past", "unknown"]
    negated: bool
    evidence: Evidence
    replaces_observation_id: str | None = None


class ConfirmedFact(StrictModel):
    observation_id: str
    source_utterance_id: str
    revision: int = Field(ge=1)
    fact: FactCandidate


class RiskCandidate(StrictModel):
    kind: Literal["fall", "cannot_stand", "pain", "help_request", "other"]
    subject: Literal["speaker", "other", "unknown"]
    temporal_scope: Literal["now", "today", "past", "unknown"]
    proposal: Literal["observe", "confirm", "correct", "dismiss"]
    episode_id: str | None = None
    evidence: Evidence


class RiskEpisodeContext(StrictModel):
    episode_id: str
    observation_ids: tuple[str, ...]
    description: str
    resolution: Literal["unresolved", "confirmed", "dismissed"]


class SemanticPayload(StrictModel):
    dialogue_act: Literal[
        "answer",
        "question",
        "correction",
        "repeat",
        "backchannel",
        "unclear",
    ]
    control: Literal["none", "stop_call", "revoke_consent", "defer", "wrong_person", "pause"]
    consent_answer: Literal["yes", "no", "unclear", "not_applicable"]
    consent_evidence: Evidence | None = None
    control_evidence: Evidence | None = None
    facts: tuple[FactCandidate, ...] = ()
    risk_candidates: tuple[RiskCandidate, ...] = ()
    answers_pending_question: bool
    needs_clarification: bool
    user_question: str | None = None


ActiveQuestionKind = Literal[
    "identity",
    "consent",
    "can_talk",
    "slot",
    "risk",
    "clarify",
    "goodbye",
    "none",
]


class TurnContext(StrictModel):
    call_id: str
    turn_id: int
    utterance_id: str
    state_version: int
    raw_text: str
    asr_quality: Literal["GOOD", "LOW", "UNUSABLE"]
    pending_question_id: str | None
    pending_question: str | None
    pending_question_delivery: Literal["complete", "partial", "unknown"]
    active_question_kind: ActiveQuestionKind = "none"
    confirmed_facts: tuple[ConfirmedFact, ...] = ()
    risk_episodes: tuple[RiskEpisodeContext, ...] = ()
    delivered_assistant_phrases: tuple[str, ...] = ()


class TurnInterpretation(StrictModel):
    context: TurnContext
    payload: SemanticPayload
    provider_request_id: str


class InterpretationProvider(Protocol):
    async def interpret_turn(
        self, context: TurnContext, *, deadline: float
    ) -> TurnInterpretation: ...


def evidence_matches(raw_text: str, evidence: Evidence) -> bool:
    return (
        evidence.start < evidence.end <= len(raw_text)
        and raw_text[evidence.start : evidence.end] == evidence.quote
    )
