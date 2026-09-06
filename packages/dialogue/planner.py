"""Planner — decides what to do next (not how to say it)."""

from packages.contracts.enums import ConsentState, FsmState, SlotStatus
from packages.contracts.mandatory import PILOT_SLOT_CHECKS
from packages.contracts.turn import TurnProposal
from packages.dialogue.facts import FactRecord
from packages.dialogue.fsm import CallFsm
from packages.dialogue.interpretation import UserInterpretation, interpret_user_turn
from packages.dialogue.state import DialogueState

_GOODBYE_CONFIRM = "Вы хотите закончить разговор?"
_GOODBYE_FINAL = "До свидания. Хорошего дня."
_GOODBYE_MARKERS = ("до свидания", "всего доброго")
_MAX_SLOT_UNCLEAR = 2

_VERA_INTRO = "Я Вера, голосовой помощник IMVERA."
_DEFER_ACK = "Поняла. Поговорим в другой раз. До свидания."
_WRONG_PERSON_FINAL = "Извините, видимо, ошиблись номером. До свидания."
_REVOKE_FINAL = "Поняла. Без вашего согласия больше не буду звонить. До свидания."
_RED_SAFETY_PROMPT = (
    "Мне важно убедиться: вы сейчас в безопасности? Нужна ли вам помощь?"
)
_SLOT_ALT_CLOSE = (
    "Кажется, сейчас не очень удобно. Можем закончить — "
    "или скажите коротко, как вы себя чувствуете?"
)

_SLOT_QUESTIONS: dict[str, str] = {
    "wellness": "Расскажите, как вы себя чувствуете сейчас?",
    "mood": "Как у вас настроение?",
    "sleep": "Как вы спали?",
    "plans": "Какие у вас планы на сегодня?",
}


class Planner:
    @staticmethod
    def plan_vera_turn(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        """Emit Vera's line for the current FSM state (call opening / re-prompt)."""
        if state.fsm_state == FsmState.CALL_START:
            state.fsm_state = FsmState.IDENTIFY_PERSON
        return Planner._prompt_for_state(state, turn_id, generation_id)

    @staticmethod
    def plan_after_user(
        state: DialogueState,
        user_text: str,
        generation_id: str,
        turn_id: int,
        interp: UserInterpretation | None = None,
    ) -> TurnProposal:
        if state.is_terminal() and state.goodbye_confirmed:
            return Planner._terminal_noop(state, turn_id, generation_id)

        if interp is None:
            interp = interpret_user_turn(state, user_text)

        if interp.revoke_consent:
            return Planner._handle_revoke_consent(state, turn_id, generation_id)

        if interp.wrong_person:
            return Planner._handle_wrong_person(state, turn_id, generation_id)

        if interp.defers_call and state.fsm_state == FsmState.CHECK_CAN_TALK:
            return Planner._handle_defer(state, turn_id, generation_id)

        if interp.asks_who_are_you:
            return Planner._handle_who_are_you(state, turn_id, generation_id)

        if interp.requests_goodbye or interp.confirms_goodbye or interp.declines_goodbye:
            return Planner._handle_closing_turn(state, user_text, turn_id, generation_id, interp)

        if interp.requests_repeat:
            return Planner._prompt_repeat(state, turn_id, generation_id)

        if interp.judgement.name == "UNCLEAR" and state.pending_slot:
            slot = state.pending_slot
            count = state.slot_unclear_counts.get(slot, 0) + 1
            state.slot_unclear_counts[slot] = count
            if count > _MAX_SLOT_UNCLEAR:
                return Planner._slot_unclear_limit(state, turn_id, generation_id)

        state = Planner._apply_interpretation(state, interp, turn_id)
        if state.consent_declined and state.fsm_state == FsmState.FINAL_CLASSIFICATION:
            return Planner._prompt_for_state(state, turn_id, generation_id)

        Planner._advance_when_ready(state)
        return Planner._prompt_for_state(state, turn_id, generation_id)

    @staticmethod
    def _terminal_noop(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech="",
            intent="terminal_noop",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
        )

    @staticmethod
    def _handle_revoke_consent(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        state.consent_declined = True
        state.call_revoked = True
        state.mandatory_checks["consent"] = False
        state.call_ended_early = True
        state.fsm_state = FsmState.FINAL_CLASSIFICATION
        state.goodbye_confirmed = True
        state.bump_version()
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=_REVOKE_FINAL,
            intent="revoke_consent_final",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
        )

    @staticmethod
    def _handle_wrong_person(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        state.wrong_person = True
        state.call_ended_early = True
        state.fsm_state = FsmState.FINAL_CLASSIFICATION
        state.goodbye_confirmed = True
        state.bump_version()
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=_WRONG_PERSON_FINAL,
            intent="wrong_person_final",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
        )

    @staticmethod
    def _handle_defer(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        state.call_deferred = True
        state.call_ended_early = True
        state.fsm_state = FsmState.FINAL_CLASSIFICATION
        state.goodbye_confirmed = True
        state.bump_version()
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=_DEFER_ACK,
            intent="defer_call_final",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
        )

    @staticmethod
    def _handle_who_are_you(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        resume = state.pending_question or ""
        if state.fsm_state == FsmState.IDENTIFY_PERSON:
            resume = f"Я разговариваю с {state.elder_display_name}?"
        elif state.fsm_state == FsmState.CHECK_CAN_TALK:
            resume = "Вам сейчас удобно немного поговорить?"
        elif state.fsm_state == FsmState.CHECK_CONSENT:
            resume = (
                "Вы согласны получать регулярные звонки от IMVERA? "
                "Это важно — звонки только с вашего согласия."
            )
        speech = f"{_VERA_INTRO} {resume}".strip()
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=speech,
            intent="explain_vera_resume",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
        )

    @staticmethod
    def _slot_unclear_limit(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=_SLOT_ALT_CLOSE,
            intent="slot_unclear_limit",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
        )

    @staticmethod
    def _advance_when_ready(state: DialogueState) -> None:
        while CallFsm.can_advance(state):
            if state.fsm_state == FsmState.GREETING and not state.greeted:
                break
            if state.fsm_state == FsmState.DAILY_CHECK and Planner._next_open_slot(state):
                break
            if state.fsm_state in (
                FsmState.SUMMARY,
                FsmState.GOODBYE,
                FsmState.FINAL_CLASSIFICATION,
            ):
                break
            CallFsm.advance(state)

    @staticmethod
    def _prompt_for_state(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        base = {
            "turn_id": turn_id,
            "generation_id": generation_id,
            "fsm_state": state.fsm_state,
            "mandatory_remaining": state.mandatory_remaining(),
        }

        if state.fsm_state == FsmState.IDENTIFY_PERSON:
            return TurnProposal(
                **base,
                speech=(
                    f"Здравствуйте. Я Вера, голосовой помощник IMVERA. "
                    f"Я разговариваю с {state.elder_display_name}?"
                ),
                intent="confirm_identity",
            )

        if state.fsm_state == FsmState.CHECK_CONSENT:
            return TurnProposal(
                **base,
                speech=(
                    "Вы согласны получать регулярные звонки от IMVERA? "
                    "Это важно — звонки только с вашего согласия."
                ),
                intent="confirm_consent",
            )

        if state.fsm_state == FsmState.GREETING:
            if not state.greeted:
                state.greeted = True
                return TurnProposal(
                    **base,
                    speech="Доброе утро. Это IMVERA, ваш регулярный звонок.",
                    intent="greeting",
                )
            Planner._advance_when_ready(state)
            return Planner._prompt_for_state(state, turn_id, generation_id)

        if state.fsm_state == FsmState.CHECK_CAN_TALK:
            return TurnProposal(
                **base,
                speech="Вам сейчас удобно немного поговорить?",
                intent="check_can_talk",
            )

        if state.fsm_state == FsmState.DAILY_CHECK:
            open_slot = Planner._next_open_slot(state)
            if open_slot:
                Planner._arm_pending_slot(state, open_slot)
                return TurnProposal(
                    **base,
                    speech=_SLOT_QUESTIONS[open_slot],
                    intent=f"check_{open_slot}",
                )

        if state.fsm_state == FsmState.SUMMARY:
            return TurnProposal(
                **base,
                speech="Спасибо за разговор.",
                intent="summary",
            )

        if state.fsm_state == FsmState.RED_SIGNAL:
            return TurnProposal(
                **base,
                speech=_RED_SAFETY_PROMPT,
                intent="red_confirm_safety",
            )

        if state.fsm_state == FsmState.FINAL_CLASSIFICATION:
            if state.consent_declined or state.call_revoked:
                return TurnProposal(
                    **base,
                    speech=_REVOKE_FINAL,
                    intent="consent_declined_final",
                )
            if state.wrong_person:
                return TurnProposal(
                    **base,
                    speech=_WRONG_PERSON_FINAL,
                    intent="wrong_person_final",
                )
            if state.call_deferred:
                return TurnProposal(
                    **base,
                    speech=_DEFER_ACK,
                    intent="defer_call_final",
                )
            return TurnProposal(
                **base,
                speech=_GOODBYE_FINAL,
                intent="goodbye_final",
            )

        return TurnProposal(
            **base,
            speech="Спасибо, что ответили.",
            intent="acknowledge",
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
    def _apply_interpretation(
        state: DialogueState,
        interp: UserInterpretation,
        turn_id: int,
    ) -> DialogueState:
        from packages.contracts.enums import AnswerJudgement

        if interp.sets_consent == ConsentState.DECLINED:
            state.consent_declined = True
            state.mandatory_checks["consent"] = False
            state.fsm_state = FsmState.FINAL_CLASSIFICATION
            state.call_ended_early = True
            state.bump_version()
            return state

        if interp.sets_consent == ConsentState.ACTIVE:
            state.mandatory_checks["consent"] = True
            state.consent_declined = False

        if interp.confirms_identity:
            state.mandatory_checks["identity"] = True

        if interp.confirms_can_talk:
            state.mandatory_checks["can_talk"] = True

        if (
            interp.fills_pending_slot
            and state.pending_slot
            and state.pending_slot in state.slots
            and interp.judgement == AnswerJudgement.VALID
        ):
            slot = state.pending_slot
            value = interp.slot_value or ""
            prev = state.facts.get(slot)
            revision = (prev.revision + 1) if prev else 1
            state.facts[slot] = FactRecord(
                field=slot,
                value=value,
                source_quote=value,
                turn_id=turn_id,
                revision=revision,
            )
            state.slots[slot] = SlotStatus.FILLED
            state.mandatory_checks[slot] = True
            state.pending_slot = None
            state.pending_question = None
            state.slot_unclear_counts.pop(slot, None)
            state.bump_version()

        return state

    @staticmethod
    def _may_enter_closing_fsm(state: DialogueState) -> bool:
        closing_states = (FsmState.SUMMARY, FsmState.GOODBYE, FsmState.FINAL_CLASSIFICATION)
        return not state.mandatory_remaining() and state.fsm_state in closing_states

    @staticmethod
    def _prompt_repeat(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        speech = state.pending_question or "Повторите, пожалуйста."
        intent = "repeat_question"
        if state.pending_slot:
            intent = f"repeat_{state.pending_slot}"
        elif state.fsm_state == FsmState.CHECK_CONSENT:
            speech = (
                "Вы согласны получать регулярные звонки от IMVERA? "
                "Это важно — звонки только с вашего согласия."
            )
            intent = "repeat_consent"
        elif state.fsm_state == FsmState.CHECK_CAN_TALK:
            speech = "Вам сейчас удобно немного поговорить?"
            intent = "repeat_can_talk"
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=speech,
            intent=intent,
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
        )

    @staticmethod
    def _handle_closing_turn(
        state: DialogueState,
        user_text: str,
        turn_id: int,
        generation_id: str,
        interp: UserInterpretation | None = None,
    ) -> TurnProposal:
        saved_fsm = state.fsm_state
        normalized = user_text.lower().strip()

        if interp and interp.declines_goodbye:
            state.awaiting_goodbye_confirm = False
            state.closing_requested = False
            state.goodbye_count = 0
            state.fsm_state = saved_fsm
            return Planner._prompt_for_state(state, turn_id, generation_id)

        if interp and interp.confirms_goodbye:
            state.goodbye_count = max(state.goodbye_count, 2)
        elif any(marker in normalized for marker in _GOODBYE_MARKERS):
            state.goodbye_count += 1
            state.closing_requested = True
        elif interp and interp.requests_goodbye:
            state.goodbye_count += 1
            state.closing_requested = True

        can_close = Planner._may_enter_closing_fsm(state)

        if state.goodbye_count >= 2 or (interp and interp.confirms_goodbye):
            state.goodbye_confirmed = True
            state.call_ended_early = bool(state.mandatory_remaining())
            state.awaiting_goodbye_confirm = False
            state.fsm_state = FsmState.FINAL_CLASSIFICATION
            state.bump_version()
            return TurnProposal(
                turn_id=turn_id,
                generation_id=generation_id,
                speech=_GOODBYE_FINAL,
                intent="goodbye_final",
                fsm_state=state.fsm_state,
                mandatory_remaining=state.mandatory_remaining(),
            )

        state.awaiting_goodbye_confirm = True
        if state.goodbye_count >= 1 and can_close and state.fsm_state == FsmState.SUMMARY:
            state.fsm_state = FsmState.GOODBYE
        elif not can_close:
            state.fsm_state = saved_fsm

        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=_GOODBYE_CONFIRM,
            intent="goodbye_confirm",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
        )

    @staticmethod
    def plan_closing(
        state: DialogueState,
        user_text: str,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        """Goodbye sub-flow — prefer plan_after_user for unified routing."""
        return Planner._handle_closing_turn(state, user_text, turn_id, generation_id)
