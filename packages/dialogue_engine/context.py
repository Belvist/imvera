"""Interpretation context and structured meaning — dialogue semantics only."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from packages.contracts.enums import FsmState, SlotStatus

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState, Question


class SlotCandidate(BaseModel):
    value: str
    polarity: str | None = None
    confidence: float = 0.9

    model_config = {"frozen": True}


class SlotValue(BaseModel):
    value: str
    confidence: float = 0.9
    source_turn_id: str = ""
    source_text: str = ""
    polarity: str | None = None
    confirmed: bool = False

    model_config = {"frozen": False}


@dataclass(frozen=True)
class InterpretContext:
    """Context for interpreting one user utterance."""

    delivered_question: Question | None
    playing_question: Question | None
    answer_slot: str | None
    open_slots: tuple[str, ...]
    filled_slots: frozenset[str]
    fsm_state: FsmState
    summary_spoken: bool = False
    awaiting_goodbye_confirm: bool = False
    turn_id: str = ""

    @classmethod
    def from_engine_state(
        cls,
        state: EngineState,
        *,
        turn_id: str = "",
    ) -> InterpretContext:
        open_slots = tuple(
            s for s in ("wellness", "mood", "sleep", "plans")
            if state.slots.get(s) == SlotStatus.OPEN
        )
        filled = frozenset(
            s for s in ("wellness", "mood", "sleep", "plans")
            if state.slots.get(s) == SlotStatus.FILLED
        )
        return cls(
            delivered_question=state.delivered_question,
            playing_question=state.playing_question,
            answer_slot=state.answer_context_slot(),
            open_slots=open_slots,
            filled_slots=filled,
            fsm_state=state.fsm_state,
            summary_spoken=state.summary_spoken,
            awaiting_goodbye_confirm=state.awaiting_goodbye_confirm,
            turn_id=turn_id,
        )


@dataclass
class ResponsePlan:
    acknowledge: str = ""
    facts_to_reference: list[str] = field(default_factory=list)
    next_slot: str | None = None
    mandatory_question: str = ""
    tone: str = "warm"


class StructuredMeaning(BaseModel):
    """Full utterance semantics — may fill multiple slots."""

    act: str  # SemanticAct value
    answers_to: str | None = None
    slots: dict[str, SlotCandidate] = Field(default_factory=dict)
    repair: bool = False
    backchannel: bool = False
    correction: bool = False
    free_facts: list[str] = Field(default_factory=list)
    raw_text: str = ""
    polarity: str | None = None
    confidence: float = 0.0

    model_config = {"frozen": True}
