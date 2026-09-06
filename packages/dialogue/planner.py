"""Planner — decides what to do next (not how to say it)."""

from packages.contracts.enums import AnswerJudgement, FsmState, SlotStatus
from packages.contracts.turn import TurnProposal
from packages.dialogue.fsm import CallFsm
from packages.dialogue.state import DialogueState

_WELLNESS_Q = "Расскажите, как вы себя чувствуете сейчас?"


class Planner:
    @staticmethod
    def plan_after_user(
        state: DialogueState,
        user_text: str,
        judgement: AnswerJudgement,
        generation_id: str,
        turn_id: int,
    ) -> TurnProposal:
        state = Planner._apply_user(state, user_text, judgement)

        if state.fsm_state == FsmState.DAILY_CHECK and state.slots["wellness"] == SlotStatus.OPEN:
            return TurnProposal(
                turn_id=turn_id,
                generation_id=generation_id,
                speech=_WELLNESS_Q,
                intent="check_wellness",
                fsm_state=state.fsm_state,
                mandatory_remaining=state.mandatory_remaining(),
            )

        if state.fsm_state == FsmState.GREETING and not state.greeted:
            state.greeted = True
            state.mandatory_checks["identity"] = True
            return TurnProposal(
                turn_id=turn_id,
                generation_id=generation_id,
                speech="Доброе утро. Это IMVERA, ваш регулярный звонок.",
                intent="greeting",
                fsm_state=state.fsm_state,
                mandatory_remaining=state.mandatory_remaining(),
            )

        state = CallFsm.advance(state)
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech="Спасибо, что ответили.",
            intent="acknowledge",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
        )

    @staticmethod
    def _apply_user(
        state: DialogueState, user_text: str, judgement: AnswerJudgement
    ) -> DialogueState:
        if (
            judgement == AnswerJudgement.VALID
            and state.pending_slot == "wellness"
            and user_text.strip()
        ):
            state.slots["wellness"] = SlotStatus.FILLED
            state.mandatory_checks["wellness"] = True
            state.pending_slot = None
            state.pending_question = None
        elif state.fsm_state == FsmState.DAILY_CHECK and state.slots["wellness"] == SlotStatus.OPEN:
            state.pending_slot = "wellness"
            state.pending_question = _WELLNESS_Q
        return state
