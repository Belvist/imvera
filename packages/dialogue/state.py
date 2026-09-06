"""Call dialogue state — sole owner of facts and slots."""

from pydantic import BaseModel, Field

from packages.contracts.enums import FsmState, SlotStatus
from packages.contracts.mandatory import PILOT_MANDATORY_CHECKS, pilot_mandatory_defaults


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
    mandatory_checks: dict[str, bool] = Field(default_factory=pilot_mandatory_defaults)
    greeted: bool = False
    goodbye_count: int = 0
    goodbye_confirmed: bool = False
    closing_requested: bool = False
    elder_display_name: str = "Анной Петровной"

    def mandatory_remaining(self) -> list[str]:
        return [k for k in PILOT_MANDATORY_CHECKS if not self.mandatory_checks.get(k, False)]
