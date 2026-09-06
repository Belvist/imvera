"""Call dialogue state — sole owner of facts and slots."""

from pydantic import BaseModel, Field

from packages.contracts.enums import FsmState, SlotStatus


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
    mandatory_checks: dict[str, bool] = Field(
        default_factory=lambda: {
            "identity": False,
            "consent": False,
            "can_talk": False,
            "wellness": False,
        }
    )
    greeted: bool = False
    closing: bool = False

    def mandatory_remaining(self) -> list[str]:
        return [k for k, v in self.mandatory_checks.items() if not v]
