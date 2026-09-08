"""DialogueEngine state — sole conversational truth for pilot daily-check flow."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from packages.contracts.enums import FsmState, SlotStatus
from packages.dialogue_engine.effects import SpeakEffect
from packages.dialogue_engine.context import SlotValue


class CheckPath(StrEnum):
    STANDARD = "standard"
    NEGATIVE_PROBE = "negative_probe"
    PAIN_SHORT = "pain_short"
    URGENT = "urgent"

MAX_SLOT_ATTEMPTS = 2


class OpeningState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PLAYING = "PLAYING"
    DELIVERED = "DELIVERED"


class QuestionPhase(StrEnum):
    PLANNED = "PLANNED"
    SYNTHESIZING = "SYNTHESIZING"
    PLAYING = "PLAYING"
    DELIVERED = "DELIVERED"
    ANSWERED = "ANSWERED"
    CANCELLED = "CANCELLED"


class Question(BaseModel):
    question_id: str
    slot: str
    text: str
    phase: QuestionPhase = QuestionPhase.PLANNED
    intent: str = ""

    model_config = {"frozen": True}


class GoalState(BaseModel):
    slot: str
    delivered_attempts: int = 0
    max_attempts: int = MAX_SLOT_ATTEMPTS
    status: SlotStatus = SlotStatus.OPEN
    reserved_question_id: str | None = None

    model_config = {"frozen": False}


class EngineState(BaseModel):
    call_id: str
    elder_display_name: str = "Анной Петровной"
    revision: int = 0

    fsm_state: FsmState = FsmState.CALL_START
    opening_state: OpeningState = OpeningState.NOT_STARTED
    opening_play_count: int = 0
    first_user_turn_received: bool = False

    slots: dict[str, SlotStatus] = Field(
        default_factory=lambda: {
            "wellness": SlotStatus.OPEN,
            "mood": SlotStatus.OPEN,
            "sleep": SlotStatus.OPEN,
            "plans": SlotStatus.OPEN,
        }
    )
    slot_values: dict[str, str] = Field(default_factory=dict)
    slot_records: dict[str, "SlotValue"] = Field(default_factory=dict)
    goals: dict[str, GoalState] = Field(default_factory=dict)

    planned_question: Question | None = None
    playing_question: Question | None = None
    delivered_question: Question | None = None
    active_playout: Question | None = None

    processing_turn_id: str | None = None
    processing_effect_id: str | None = None
    active_playout_generation: int = 0

    slot_unclear_counts: dict[str, int] = Field(default_factory=dict)
    waiting_on_slot: str | None = None
    summary_spoken: bool = False
    awaiting_goodbye_confirm: bool = False
    goodbye_confirmed: bool = False
    goodbye_count: int = 0
    call_closed: bool = False
    closing_reason: str | None = None

    turn_seq: int = 0
    generation_seq: int = 0
    deferred_speak: SpeakEffect | None = None
    slot_corrections: list[dict[str, str]] = Field(default_factory=list)

    check_path: CheckPath = CheckPath.STANDARD
    probe_phase: str | None = None
    skipped_slots: set[str] = Field(default_factory=set)
    wellness_concern: str = ""
    wellness_duration: str = ""
    pain_at_night: str = ""
    prior_call_context: dict[str, str] = Field(default_factory=dict)
    follow_up_opening: bool = False
    wellness_probes_enabled: bool = True

    def bump_revision(self) -> None:
        self.revision += 1

    def next_generation_id(self) -> str:
        self.generation_seq += 1
        return f"g-{self.generation_seq}"

    def ensure_goal(self, slot: str) -> GoalState:
        goal = self.goals.get(slot)
        if goal is None:
            goal = GoalState(slot=slot)
            self.goals[slot] = goal
        return goal

    def answer_context_slot(self) -> str | None:
        """Slot used to interpret the next user answer — delivered, not planned."""
        if self.probe_phase:
            return f"probe_{self.probe_phase}"
        if self.delivered_question is not None:
            return self.delivered_question.slot
        if self.playing_question is not None:
            return self.playing_question.slot
        return None

    def next_open_slot(self) -> str | None:
        if self.check_path == CheckPath.URGENT:
            return None
        for slot in ("wellness", "mood", "sleep", "plans"):
            if slot in self.skipped_slots:
                continue
            if self.slots.get(slot) == SlotStatus.OPEN:
                return slot
        return None
