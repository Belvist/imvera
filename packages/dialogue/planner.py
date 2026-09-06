"""Planner — decides what to do next (not how to say it)."""

from packages.contracts.enums import AnswerJudgement, FsmState, SlotStatus
from packages.contracts.mandatory import PILOT_SLOT_CHECKS
from packages.contracts.turn import TurnProposal
from packages.dialogue.fsm import CallFsm
from packages.dialogue.state import DialogueState

_WELLNESS_Q = "Расскажите, как вы себя чувствуете сейчас?"
_GOODBYE_CONFIRM = "Вы хотите закончить разговор?"
_GOODBYE_FINAL = "До свидания. Хорошего дня."
_GOODBYE_MARKERS = ("до свидания", "пока", "всего доброго")

_SLOT_QUESTIONS: dict[str, str] = {
    "wellness": _WELLNESS_Q,
    "mood": "Как у вас настроение?",
    "sleep": "Как вы спали?",
    "plans": "Какие у вас планы на сегодня?",
}


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

        open_slot = Planner._next_open_slot(state)
        if state.fsm_state == FsmState.DAILY_CHECK and open_slot:
            Planner._arm_pending_slot(state, open_slot)
            return TurnProposal(
                turn_id=turn_id,
                generation_id=generation_id,
                speech=_SLOT_QUESTIONS[open_slot],
                intent=f"check_{open_slot}",
                fsm_state=state.fsm_state,
                mandatory_remaining=state.mandatory_remaining(),
            )

        if state.fsm_state == FsmState.GREETING and not state.greeted:
            state.greeted = True
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
    def _arm_pending_slot(state: DialogueState, slot: str) -> None:
        state.pending_slot = slot
        state.pending_question = _SLOT_QUESTIONS[slot]

    @staticmethod
    def _next_open_slot(state: DialogueState) -> str | None:
        for slot in PILOT_SLOT_CHECKS:
            if state.slots[slot] == SlotStatus.OPEN:
                return slot
        return None

    @staticmethod
    def _apply_user(
        state: DialogueState, user_text: str, judgement: AnswerJudgement
    ) -> DialogueState:
        if judgement == AnswerJudgement.VALID and user_text.strip():
            if state.fsm_state == FsmState.IDENTIFY_PERSON:
                state.mandatory_checks["identity"] = True
            elif state.fsm_state == FsmState.CHECK_CONSENT:
                state.mandatory_checks["consent"] = True
            elif state.fsm_state == FsmState.CHECK_CAN_TALK:
                state.mandatory_checks["can_talk"] = True
            elif state.pending_slot and state.pending_slot in state.slots:
                state.slots[state.pending_slot] = SlotStatus.FILLED
                state.mandatory_checks[state.pending_slot] = True
                state.pending_slot = None
                state.pending_question = None
        elif judgement in (AnswerJudgement.NO_ANSWER, AnswerJudgement.BACKCHANNEL):
            pass
        return state

    @staticmethod
    def plan_closing(
        state: DialogueState,
        user_text: str,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        """Goodbye sub-flow: first goodbye → confirm; second → terminal (S12)."""
        if state.fsm_state not in (
            FsmState.SUMMARY,
            FsmState.GOODBYE,
            FsmState.FINAL_CLASSIFICATION,
        ):
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
