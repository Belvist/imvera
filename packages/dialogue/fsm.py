"""Minimal FSM transitions — expand in Phase 2+."""

from packages.contracts.enums import FsmState
from packages.dialogue.state import DialogueState

_TRANSITIONS: dict[FsmState, FsmState] = {
    FsmState.CALL_START: FsmState.IDENTIFY_PERSON,
    FsmState.IDENTIFY_PERSON: FsmState.CHECK_CONSENT,
    FsmState.CHECK_CONSENT: FsmState.GREETING,
    FsmState.GREETING: FsmState.CHECK_CAN_TALK,
    FsmState.CHECK_CAN_TALK: FsmState.DAILY_CHECK,
    FsmState.DAILY_CHECK: FsmState.FOLLOW_UP,
    FsmState.FOLLOW_UP: FsmState.RISK_REVIEW,
    FsmState.RISK_REVIEW: FsmState.SUMMARY,
    FsmState.SUMMARY: FsmState.GOODBYE,
    FsmState.GOODBYE: FsmState.FINAL_CLASSIFICATION,
}


class CallFsm:
    @staticmethod
    def can_advance(state: DialogueState) -> bool:
        if state.fsm_state == FsmState.DAILY_CHECK and state.mandatory_remaining():
            return False
        if state.fsm_state in (FsmState.SUMMARY, FsmState.GOODBYE):
            return not state.mandatory_remaining()
        return True

    @staticmethod
    def advance(state: DialogueState) -> DialogueState:
        if not CallFsm.can_advance(state):
            return state
        nxt = _TRANSITIONS.get(state.fsm_state)
        if nxt:
            state.fsm_state = nxt
        return state

    @staticmethod
    def interrupt_red(state: DialogueState) -> DialogueState:
        state.fsm_state = FsmState.RED_SIGNAL
        return state
