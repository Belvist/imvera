"""Planner — decides what to do next (not how to say it)."""

from packages.contracts.enums import AnswerJudgement, FsmState, SlotStatus
from packages.contracts.turn import TurnProposal
from packages.dialogue.fsm import CallFsm
from packages.dialogue.state import DialogueState

_WELLNESS_Q = "Расскажите, как вы себя чувствуете сейчас?"
_GOODBYE_CONFIRM = "Вы хотите закончить разговор?"
_GOODBYE_FINAL = "До свидания. Хорошего дня."
_GOODBYE_MARKERS = ("до свидания", "пока", "всего доброго")


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
        elif judgement in (AnswerJudgement.NO_ANSWER, AnswerJudgement.BACKCHANNEL):
            # Silence / backchannel never close an open slot (DIALOGUE_SPEC, S11).
            pass
        elif state.fsm_state == FsmState.DAILY_CHECK and state.slots["wellness"] == SlotStatus.OPEN:
            state.pending_slot = "wellness"
            state.pending_question = _WELLNESS_Q
        return state

    @staticmethod
    def plan_closing(
        state: DialogueState,
        user_text: str,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        """Goodbye sub-flow: first goodbye → confirm; second → terminal (S12)."""
        if state.fsm_state not in (FsmState.SUMMARY, FsmState.GOODBYE, FsmState.FINAL_CLASSIFICATION):
            state.fsm_state = FsmState.GOODBYE

        normalized = user_text.lower().strip()
        if any(marker in normalized for marker in _GOODBYE_MARKERS):
            state.goodbye_count += 1
            if state.fsm_state == FsmState.SUMMARY:
                state.fsm_state = FsmState.GOODBYE

        if state.goodbye_count >= 2:
            state.goodbye_confirmed = True
            state.fsm_state = FsmState.FINAL_CLASSIFICATION
            return TurnProposal(
                turn_id=turn_id,
                generation_id=generation_id,
                speech=_GOODBYE_FINAL,
                intent="goodbye_final",
                fsm_state=state.fsm_state,
                mandatory_remaining=state.mandatory_remaining(),
            )

        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=_GOODBYE_CONFIRM,
            intent="goodbye_confirm",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
        )
