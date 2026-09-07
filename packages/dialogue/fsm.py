"""FSM transitions with mandatory exit gates."""

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

_EXIT_GATES: dict[FsmState, str] = {
    FsmState.IDENTIFY_PERSON: "identity",
    FsmState.CHECK_CONSENT: "consent",
    FsmState.CHECK_CAN_TALK: "can_talk",
}


class CallFsm:
    @staticmethod
    def can_advance(state: DialogueState) -> bool:
        gate_key = _EXIT_GATES.get(state.fsm_state)
        if gate_key and not state.mandatory_checks.get(gate_key, False):
            return False
        if state.fsm_state == FsmState.GREETING and not state.greeted:
            return False
        if state.fsm_state == FsmState.DAILY_CHECK:
            from packages.dialogue.question_ledger import next_open_slot

            if next_open_slot(state.slots):
                return False
        if state.fsm_state in (FsmState.SUMMARY, FsmState.GOODBYE):
            return not state.mandatory_remaining()
        if state.fsm_state in (
            FsmState.FINAL_CLASSIFICATION,
            FsmState.RED_SIGNAL,
            FsmState.CONFIRM_SITUATION,
            FsmState.INCIDENT_REQUESTED,
            FsmState.ESCALATION_HANDOFF,
        ):
            return False
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
    def interrupt_red(
        state: DialogueState,
        source_quote: str | None = None,
        episode_id: str | None = None,
    ) -> DialogueState:
        state.fsm_state = FsmState.RED_SIGNAL
        state.risk_handling = True
        if source_quote:
            state.risk_source_quote = source_quote
        if episode_id:
            state.risk_episode_id = episode_id
        return state
