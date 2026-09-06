"""Call dialogue state — sole owner of facts and slots."""

from pydantic import BaseModel, Field

from packages.contracts.enums import FsmState, SlotStatus
from packages.contracts.mandatory import PILOT_MANDATORY_CHECKS, pilot_mandatory_defaults
from packages.dialogue.facts import FactRecord


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
    slot_unclear_counts: dict[str, int] = Field(default_factory=dict)

    def bump_version(self) -> None:
        self.state_version += 1

    def mandatory_remaining(self) -> list[str]:
        return [k for k in PILOT_MANDATORY_CHECKS if not self.mandatory_checks.get(k, False)]

    def is_terminal(self) -> bool:
        return self.fsm_state in (
            FsmState.FINAL_CLASSIFICATION,
            FsmState.ESCALATION_HANDOFF,
        )
