"""Typed turn interpretation contract — hypotheses, not committed facts."""

from pydantic import BaseModel, Field

from packages.contracts.enums import AnswerJudgement, AsrQuality, DialogueAct


class FactCandidate(BaseModel):
    """Proposed fact from a user turn; policy layer commits or rejects."""

    field: str
    value: str
    subject: str = "elder"
    negated: bool = False
    source_quote: str
    answers_pending: bool = True


class TurnInterpretation(BaseModel):
    """Structured meaning of one user turn before state mutation."""

    call_id: str
    turn_id: int
    raw_text: str
    asr_quality: AsrQuality = AsrQuality.GOOD
    state_version: int = 0
    dialogue_act: DialogueAct
    judgement: AnswerJudgement
    fact_candidates: list[FactCandidate] = Field(default_factory=list)
    answers_pending_question: bool = False
    ambiguous: bool = False
    risk_signal_ids: list[str] = Field(default_factory=list)
