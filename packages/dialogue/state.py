"""Call dialogue state — sole owner of facts and slots."""

from pydantic import BaseModel, Field

from packages.contracts.core import TerminationReason
from packages.contracts.enums import FsmState, GoalStatus, SlotStatus
from packages.contracts.mandatory import PILOT_MANDATORY_CHECKS, pilot_mandatory_defaults
from packages.dialogue.facts import FactRecord
from packages.dialogue.question_ledger import (
    QuestionGoal,
    new_goal,
    semantic_key_for_slot,
    slot_status_from_goal,
)


class DialogueState(BaseModel):
    call_id: str
    fsm_state: FsmState = FsmState.CALL_START
    pending_slot: str | None = None
    pending_question: str | None = None
    slots: dict[str, SlotStatus] = Field(
        default_factory=lambda: {
            "wellness": SlotStatus.OPEN,
            "mood": SlotStatus.OPEN,
            "sleep": SlotStatus.OPEN,
            "plans": SlotStatus.OPEN,
        }
    )
    facts: dict[str, FactRecord] = Field(default_factory=dict)
    mandatory_checks: dict[str, bool] = Field(default_factory=pilot_mandatory_defaults)
    greeted: bool = False
    goodbye_count: int = 0
    goodbye_confirmed: bool = False
    closing_requested: bool = False
    awaiting_goodbye_confirm: bool = False
    call_ended_early: bool = False
    consent_declined: bool = False
    call_revoked: bool = False
    wrong_person: bool = False
    call_deferred: bool = False
    elder_display_name: str = "Анной Петровной"
    state_version: int = 0
    risk_handling: bool = False
    risk_source_quote: str | None = None
    risk_episode_id: str | None = None
    summary_spoken: bool = False
    final_action_done: bool = False
    call_finalized: bool = False
    termination_reason: TerminationReason | None = None
    family_id: str = ""
    slot_unclear_counts: dict[str, int] = Field(default_factory=dict)
    pending_question_delivered: bool = False
    last_committed_utterance_id: str = ""
    question_ledger: dict[str, QuestionGoal] = Field(default_factory=dict)
    waiting_on_goal: str | None = None
    consecutive_unresolved_goals: int = 0
    pending_action_id: str | None = None

    def bump_version(self) -> None:
        self.state_version += 1

    def mandatory_remaining(self) -> list[str]:
        return [k for k in PILOT_MANDATORY_CHECKS if not self.mandatory_checks.get(k, False)]

    def ensure_goal(self, slot: str) -> QuestionGoal:
        key = semantic_key_for_slot(slot)
        goal = self.question_ledger.get(key)
        if goal is None:
            goal = new_goal(slot)
            self.question_ledger[key] = goal
        return goal

    def get_goal(self, slot: str) -> QuestionGoal | None:
        return self.question_ledger.get(semantic_key_for_slot(slot))

    def sync_slot_from_goal(self, slot: str) -> None:
        goal = self.get_goal(slot)
        if goal is not None:
            self.slots[slot] = slot_status_from_goal(goal)

    def is_terminal(self) -> bool:
        return self.fsm_state in (
            FsmState.FINAL_CLASSIFICATION,
            FsmState.ESCALATION_HANDOFF,
        )
