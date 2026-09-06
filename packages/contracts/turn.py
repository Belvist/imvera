"""Turn contracts — Planner/Renderer → Validator."""

from pydantic import BaseModel, Field

from packages.contracts.enums import AnswerJudgement, FsmState


class TurnProposal(BaseModel):
    """Proposed assistant turn before Validator."""

    turn_id: int
    generation_id: str
    speech: str
    intent: str
    semantic_signals: list[str] = Field(default_factory=list)
    answer_judgement: AnswerJudgement | None = None
    fsm_state: FsmState
    mandatory_remaining: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)


class ValidatedTurn(BaseModel):
    """Approved turn ready for TTS."""

    turn_id: int
    generation_id: str
    speech: str
    intent: str
    fsm_state: FsmState
    allowed: bool = True
    validator_notes: str | None = None
