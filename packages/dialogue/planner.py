"""Planner — decides what to do next (not how to say it)."""

import re

from packages.contracts.core import TerminationReason
from packages.contracts.enums import AnswerJudgement, AsrQuality, FsmState, GoalStatus, SlotStatus
from packages.contracts.turn import TurnProposal
from packages.dialogue.fsm import CallFsm
from packages.dialogue.interpretation import UserInterpretation, interpret_user_turn
from packages.dialogue.question_ledger import (
    clarification_for_slot,
    next_open_slot,
)
from packages.dialogue.reducer import DialogueReducer
from packages.dialogue.state import DialogueState
from packages.dialogue_engine import questions

_GOODBYE_CONFIRM = "Вы хотите закончить разговор?"
_GOODBYE_FINAL = "До свидания. Хорошего дня."
_GOODBYE_MARKERS = ("до свидания", "всего доброго")


def direct_wellness_opening_enabled() -> bool:
    """Backward-compat alias: canonical home is dialogue_engine.runtime
    (Cut 3b keeps the engine-active check planner-free)."""
    from packages.dialogue_engine.runtime import (
        direct_wellness_opening_enabled as _canonical,
    )

    return _canonical()


_MAX_SLOT_UNCLEAR = 2
_STT_GARBAGE_PHRASES = frozenset(
    {
        "ответ",
        "пять вы",
        "сд",
        "сейчас",
    }
)

_VERA_INTRO = f"Я Вера, голосовой помощник сервиса {questions.service_spoken_name()}."
_DEFER_ACK = "Поняла. Поговорим в другой раз. До свидания."
_WRONG_PERSON_FINAL = "Извините, видимо, ошиблись номером. До свидания."
_REVOKE_FINAL = "Поняла. Без вашего согласия больше не буду звонить. До свидания."
_RED_SAFETY_PROMPT = "Расскажите, что произошло? Правильно ли я понимаю ситуацию?"
_RED_CLARIFY = "Спасибо за уточнение."
_RED_FALSE_ALARM_ACK = "Поняла, это относилось к другому человеку."
_SLOT_ALT_CLOSE = (
    "Кажется, сейчас не очень удобно. Можем закончить — "
    "или скажите коротко, как вы себя чувствуете?"
)
_PARTIAL_UNRESOLVED_CLOSE = "Сейчас не получилось узнать, как у вас дела. До свидания."
_PAUSE_ACK = "Подожду."

_SLOT_QUESTIONS: dict[str, str] = {
    "wellness": "Расскажите, как вы себя чувствуете сейчас?",
    "mood": "Как у вас настроение?",
    "sleep": "Как вы спали?",
    "plans": "Какие у вас планы на сегодня?",
}

_COMPLAINT_MARKERS = re.compile(
    r"\b(болит|болел\w*|болела|больно|плохо\s+спал\w*|не\s+спал\w*|"
    r"одинок\w*|грустн\w*|устал\w*|тошнит|кружится\s+голова|"
    r"плохо|не\s+очень|нехорошо)\b",
    re.I,
)
_POSITIVE_ONLY = re.compile(
    r"^(нормально|хорошо|отлично|не\s+плохо|вс[её]\s+хорошо)\.?$",
    re.I,
)


class Planner:
    @staticmethod
    def _opening_wellness_speech(state: DialogueState) -> str:
        name = state.elder_display_name
        return (
            f"Здравствуйте. Это сервис {questions.service_spoken_name()}. "
            f"{name}, Как вы себя чувствуете?"
        )

    @staticmethod
    def _begin_direct_daily_check(state: DialogueState) -> None:
        """Lab direct-open: skip verbal identity/consent/can_talk; start wellness."""
        state.fsm_state = FsmState.DAILY_CHECK
        state.greeted = True
        state.mandatory_checks["identity"] = True
        state.mandatory_checks["consent"] = True
        state.mandatory_checks["can_talk"] = True

    @staticmethod
    def _plan_opening_wellness(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        speech = Planner._opening_wellness_speech(state)
        Planner._arm_pending_slot(state, "wellness", question=speech)
        goal = state.ensure_goal("wellness")
        state.opening_play_count += 1
        if not Planner.reserve_question_attempt(state, generation_id, "wellness"):
            return Planner._mark_goal_unresolved(state, "wellness", turn_id, generation_id)
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=speech,
            intent="opening_wellness",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
            question_goal_id=goal.goal_id,
        )

    @staticmethod
    def plan_vera_turn(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        """Emit Vera's line for the current FSM state (call opening / re-prompt)."""
        if state.first_user_turn_received or state.opening_delivered:
            return Planner._prompt_for_state(state, turn_id, generation_id)
        if state.fsm_state == FsmState.CALL_START:
            if direct_wellness_opening_enabled():
                Planner._begin_direct_daily_check(state)
                return Planner._plan_opening_wellness(state, turn_id, generation_id)
            state.fsm_state = FsmState.IDENTIFY_PERSON
            return Planner._prompt_for_state(state, turn_id, generation_id)
        return Planner._prompt_for_state(state, turn_id, generation_id)

    @staticmethod
    def plan_identity_question(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        """Identity question immediately after intro audio completes."""
        state.identity_intro_spoken = True
        question = f"Я разговариваю с {state.elder_display_name}?"
        state.pending_question = question
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=question,
            intent="confirm_identity",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
        )

    @staticmethod
    def _normalize_stt_key(text: str) -> str:
        return re.sub(r"[^\wа-яё]+", "", text.strip().casefold())

    @staticmethod
    def _looks_like_stt_garbage(user_text: str) -> bool:
        key = Planner._normalize_stt_key(user_text)
        if not key:
            return True
        return key in _STT_GARBAGE_PHRASES

    @staticmethod
    def plan_after_user(
        state: DialogueState,
        user_text: str,
        generation_id: str,
        turn_id: int,
        interp: UserInterpretation | None = None,
        *,
        utterance_id: str = "",
        asr_quality: AsrQuality = AsrQuality.GOOD,
    ) -> TurnProposal:
        if state.is_terminal() and state.goodbye_confirmed:
            return Planner._terminal_noop(state, turn_id, generation_id)

        if interp is None:
            interp = interpret_user_turn(state, user_text)

        if (
            asr_quality in (AsrQuality.LOW, AsrQuality.UNUSABLE)
            and state.pending_slot
            and not state.risk_handling
        ):
            return Planner._ask_slot_question(
                state,
                state.pending_slot,
                turn_id,
                generation_id,
                clarification=True,
            )

        if (
            Planner._looks_like_stt_garbage(user_text)
            and state.pending_slot
            and not state.risk_handling
        ):
            return Planner._ask_slot_question(
                state,
                state.pending_slot,
                turn_id,
                generation_id,
                clarification=True,
            )

        if interp.revoke_consent:
            return Planner._handle_revoke_consent(state, turn_id, generation_id)

        if interp.wrong_person:
            return Planner._handle_wrong_person(state, turn_id, generation_id)

        if interp.defers_call and not state.is_terminal():
            return Planner._handle_defer(state, turn_id, generation_id)

        if interp.pause_requested and not state.is_terminal():
            return Planner._handle_pause(state, turn_id, generation_id)

        if (
            interp.declines
            and state.fsm_state == FsmState.CHECK_CAN_TALK
            and not state.mandatory_checks.get("can_talk")
        ):
            return Planner._handle_can_talk_decline(state, turn_id, generation_id)

        if interp.fact_candidates:
            DialogueReducer.apply(
                state, interp, turn_id, utterance_id=utterance_id, apply_facts=True
            )
            if not interp.asks_who_are_you:
                reflection = Planner._try_complaint_reflection(
                    state, turn_id, generation_id, interp
                )
                if reflection is not None:
                    return reflection

        if interp.asks_who_are_you:
            return Planner._handle_who_are_you(state, turn_id, generation_id)

        if interp.requests_goodbye or interp.confirms_goodbye or interp.declines_goodbye:
            return Planner._handle_closing_turn(state, user_text, turn_id, generation_id, interp)

        if interp.requests_repeat:
            return Planner._prompt_repeat(state, turn_id, generation_id)

        if state.fsm_state in (FsmState.RED_SIGNAL, FsmState.CONFIRM_SITUATION):
            return Planner._handle_risk_turn(state, interp, turn_id, generation_id)

        if (
            interp.judgement == AnswerJudgement.BACKCHANNEL
            and state.pending_slot
            and state.fsm_state == FsmState.DAILY_CHECK
            and not state.risk_handling
        ):
            return Planner._handle_backchannel_on_active_goal(
                state, turn_id, generation_id
            )

        if (
            interp.judgement.name == "UNCLEAR"
            and state.pending_slot
            and not state.risk_handling
        ):
            slot = state.pending_slot
            count = state.slot_unclear_counts.get(slot, 0) + 1
            state.slot_unclear_counts[slot] = count
            if count > _MAX_SLOT_UNCLEAR:
                return Planner._slot_unclear_limit(state, turn_id, generation_id)

        DialogueReducer.apply(
            state, interp, turn_id, utterance_id=utterance_id, apply_facts=False
        )
        if state.consent_declined and state.fsm_state == FsmState.FINAL_CLASSIFICATION:
            return Planner._prompt_for_state(state, turn_id, generation_id)

        Planner._advance_when_ready(state)
        return Planner._prompt_for_state(state, turn_id, generation_id)

    @staticmethod
    def plan_wait_expired(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        """After backchannel wait window — spend attempt or mark goal UNRESOLVED."""
        slot = state.waiting_on_goal
        state.waiting_on_goal = None
        if not slot or state.fsm_state != FsmState.DAILY_CHECK:
            Planner._advance_when_ready(state)
            return Planner._prompt_for_state(state, turn_id, generation_id)

        goal = state.ensure_goal(slot)
        if goal.status != GoalStatus.OPEN:
            Planner._advance_when_ready(state)
            return Planner._prompt_for_state(state, turn_id, generation_id)

        if goal.automatic_attempts_used >= goal.max_automatic_attempts:
            return Planner._mark_goal_unresolved(state, slot, turn_id, generation_id)

        return Planner._ask_slot_question(
            state,
            slot,
            turn_id,
            generation_id,
            clarification=True,
        )

    @staticmethod
    def reserve_question_attempt(state: DialogueState, generation_id: str, slot: str) -> bool:
        """Atomically reserve an attempt before TTS. Returns False if budget exhausted."""
        goal = state.ensure_goal(slot)
        if goal.status != GoalStatus.OPEN:
            return False
        if goal.reserved_attempt_id == generation_id:
            return True
        if goal.reserved_attempt_id is not None:
            return False
        if goal.automatic_attempts_used >= goal.max_automatic_attempts:
            return False
        goal.reserved_attempt_id = generation_id
        state.pending_action_id = generation_id
        state.bump_version()
        return True

    @staticmethod
    def mark_question_delivered(state: DialogueState, generation_id: str) -> None:
        """Count attempt when question audio may reach the channel."""
        slot = state.pending_slot
        if not slot:
            return
        goal = state.get_goal(slot)
        if goal is None or goal.reserved_attempt_id != generation_id:
            return
        if goal.automatic_attempts_used < goal.max_automatic_attempts:
            goal.automatic_attempts_used += 1
        goal.last_question_id = generation_id
        goal.last_delivery_state = "may_have_reached_channel"
        goal.audio_may_have_reached_channel = True
        goal.reserved_attempt_id = None
        state.pending_question_delivered = True
        state.delivered_answer_slot = slot
        state.pending_action_id = None
        if slot == "wellness" and state.opening_play_count > 0:
            state.opening_delivered = True
        state.bump_version()

    @staticmethod
    def release_question_attempt(state: DialogueState, generation_id: str) -> None:
        """Drop reservation when question audio never reached the channel."""
        slot = state.pending_slot
        if not slot:
            return
        goal = state.get_goal(slot)
        if goal is None or goal.reserved_attempt_id != generation_id:
            return
        goal.reserved_attempt_id = None
        if state.pending_action_id == generation_id:
            state.pending_action_id = None
        state.bump_version()

    @staticmethod
    def _is_complaint_report(value: str, *, negated: bool = False) -> bool:
        if negated:
            return False
        lower = value.strip().lower()
        if _POSITIVE_ONLY.match(lower):
            return False
        return bool(_COMPLAINT_MARKERS.search(lower))

    @staticmethod
    def _build_complaint_reflection(candidates: list) -> str:
        parts: list[str] = []
        for cand in candidates:
            text = cand.value.strip().rstrip(".!?…")
            if text:
                parts.append(text[0].lower() + text[1:] if len(text) > 1 else text.lower())
        if not parts:
            return ""
        if len(parts) == 1:
            sentence = parts[0]
        else:
            sentence = ", ".join(parts[:-1]) + f", и {parts[-1]}"
        return sentence[0].upper() + sentence[1:] + "."

    @staticmethod
    def _try_complaint_reflection(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
        interp: UserInterpretation,
    ) -> TurnProposal | None:
        if state.fsm_state != FsmState.DAILY_CHECK or state.risk_handling:
            return None
        if state.last_reflected_turn_id == turn_id:
            return None
        complaints = [
            c
            for c in interp.fact_candidates
            if Planner._is_complaint_report(c.value, negated=c.negated)
        ]
        if not complaints:
            return None
        speech = Planner._build_complaint_reflection(complaints)
        if not speech:
            return None
        state.last_reflected_turn_id = turn_id
        state.bump_version()
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=speech,
            intent="reflect_report",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
            semantic_signals=["concerned_reflection"],
        )

    @staticmethod
    def _handle_backchannel_on_active_goal(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        slot = state.pending_slot
        if not slot:
            Planner._advance_when_ready(state)
            return Planner._prompt_for_state(state, turn_id, generation_id)

        goal = state.ensure_goal(slot)
        state.waiting_on_goal = slot
        state.bump_version()
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech="",
            intent="wait_for_continuation",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
            wait_goal_id=goal.goal_id,
            semantic_signals=["backchannel_continue"],
        )

    @staticmethod
    def _mark_goal_unresolved(
        state: DialogueState,
        slot: str,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        goal = state.ensure_goal(slot)
        goal.status = GoalStatus.UNRESOLVED
        goal.reserved_attempt_id = None
        state.slots[slot] = SlotStatus.UNRESOLVED
        state.mandatory_checks[slot] = True
        state.pending_slot = None
        state.pending_question = None
        state.pending_question_delivered = False
        state.waiting_on_goal = None
        state.slot_unclear_counts.pop(slot, None)
        state.consecutive_unresolved_goals += 1
        state.call_ended_early = True
        state.final_action_done = True
        state.goodbye_confirmed = True
        state.termination_reason = TerminationReason.PARTIAL
        state.fsm_state = FsmState.FINAL_CLASSIFICATION
        state.bump_version()
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=_PARTIAL_UNRESOLVED_CLOSE,
            intent="partial_unresolved_close",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
        )

    @staticmethod
    def _ask_slot_question(
        state: DialogueState,
        slot: str,
        turn_id: int,
        generation_id: str,
        *,
        clarification: bool = False,
    ) -> TurnProposal:
        speech = (
            clarification_for_slot(slot)
            if clarification
            else _SLOT_QUESTIONS[slot]
        )
        Planner._arm_pending_slot(state, slot, question=speech)
        goal = state.ensure_goal(slot)
        if (
            goal.reserved_attempt_id
            and goal.reserved_attempt_id != generation_id
            and not state.pending_question_delivered
        ):
            Planner.release_question_attempt(state, goal.reserved_attempt_id)
        if not Planner.reserve_question_attempt(state, generation_id, slot):
            return Planner._mark_goal_unresolved(state, slot, turn_id, generation_id)
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=speech,
            intent=f"check_{slot}" if not clarification else f"clarify_{slot}",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
            question_goal_id=goal.goal_id,
        )

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
        state.final_action_done = True
        state.termination_reason = TerminationReason.CONSENT_REVOKED
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
        state.final_action_done = True
        state.termination_reason = TerminationReason.WRONG_PERSON
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
    def _handle_risk_turn(
        state: DialogueState,
        interp: UserInterpretation,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        if interp.risk_false_alarm:
            state.fsm_state = FsmState.DAILY_CHECK
            state.risk_handling = False
            state.risk_source_quote = None
            state.bump_version()
            return TurnProposal(
                turn_id=turn_id,
                generation_id=generation_id,
                fsm_state=state.fsm_state,
                mandatory_remaining=state.mandatory_remaining(),
                speech=_RED_FALSE_ALARM_ACK,
                intent="red_false_alarm",
            )
        if state.fsm_state == FsmState.RED_SIGNAL and interp.affirms:
            state.fsm_state = FsmState.CONFIRM_SITUATION
            state.bump_version()
            quote = state.risk_source_quote or "ваше сообщение"
            return TurnProposal(
                turn_id=turn_id,
                generation_id=generation_id,
                fsm_state=state.fsm_state,
                mandatory_remaining=state.mandatory_remaining(),
                speech=f"Правильно я поняла: {quote}?",
                intent="red_clarify_confirm",
            )
        if state.fsm_state == FsmState.CONFIRM_SITUATION and interp.affirms:
            state.fsm_state = FsmState.DAILY_CHECK
            state.risk_handling = False
            state.bump_version()
            return Planner._prompt_for_state(state, turn_id, generation_id)
        if state.fsm_state == FsmState.CONFIRM_SITUATION:
            return TurnProposal(
                turn_id=turn_id,
                generation_id=generation_id,
                fsm_state=state.fsm_state,
                mandatory_remaining=state.mandatory_remaining(),
                speech=_RED_CLARIFY,
                intent="red_clarified",
            )
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
            speech=_RED_SAFETY_PROMPT,
            intent="red_confirm_safety",
        )

    @staticmethod
    def _handle_can_talk_decline(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        state.mandatory_checks["can_talk"] = False
        state.call_ended_early = True
        state.fsm_state = FsmState.FINAL_CLASSIFICATION
        state.goodbye_confirmed = True
        state.final_action_done = True
        state.termination_reason = TerminationReason.DEFERRED
        state.bump_version()
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=_DEFER_ACK,
            intent="can_talk_declined_final",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
        )

    @staticmethod
    def _handle_pause(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        state.waiting_on_goal = None
        state.bump_version()
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=_PAUSE_ACK,
            intent="pause_ack",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
            semantic_signals=["pause_wait"],
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
        state.final_action_done = True
        state.termination_reason = TerminationReason.DEFERRED
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
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=_VERA_INTRO,
            intent="explain_vera",
            fsm_state=state.fsm_state,
            mandatory_remaining=state.mandatory_remaining(),
        )

    @staticmethod
    def _slot_unclear_limit(
        state: DialogueState,
        turn_id: int,
        generation_id: str,
    ) -> TurnProposal:
        slot = state.pending_slot
        if slot:
            return Planner._mark_goal_unresolved(state, slot, turn_id, generation_id)
        return TurnProposal(
            turn_id=turn_id,
            generation_id=generation_id,
            speech=_PARTIAL_UNRESOLVED_CLOSE,
            intent="partial_unresolved_close",
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
            question = f"Я разговариваю с {state.elder_display_name}?"
            state.pending_question = question
            if not state.identity_intro_spoken:
                return TurnProposal(
                    **base,
                    speech="Здравствуйте. Я Вера, голосовой помощник сервиса Амвера.",
                    intent="identity_intro",
                )
            if state.pending_question_delivered:
                speech = f"Извините, не расслышала. {question}"
                intent = "repeat_identity"
            else:
                speech = question
                intent = "confirm_identity"
            return TurnProposal(**base, speech=speech, intent=intent)

        if state.fsm_state == FsmState.CHECK_CONSENT:
            question = (
                "Вы согласны получать регулярные звонки от Амвера? "
                "Это важно — звонки только с вашего согласия."
            )
            state.pending_question = question
            return TurnProposal(
                **base,
                speech=question,
                intent="confirm_consent",
            )

        if state.fsm_state == FsmState.GREETING:
            if not state.greeted:
                state.greeted = True
                return TurnProposal(
                    **base,
                    speech="Доброе утро. Это сервис Амвера, ваш регулярный звонок.",
                    intent="greeting",
                )
            Planner._advance_when_ready(state)
            return Planner._prompt_for_state(state, turn_id, generation_id)

        if state.fsm_state == FsmState.CHECK_CAN_TALK:
            question = "Вам сейчас удобно немного поговорить?"
            state.pending_question = question
            return TurnProposal(
                **base,
                speech=question,
                intent="check_can_talk",
            )

        if state.fsm_state == FsmState.DAILY_CHECK:
            open_slot = Planner._next_open_slot(state)
            if open_slot:
                return Planner._ask_slot_question(
                    state, open_slot, turn_id, generation_id
                )

        if state.fsm_state == FsmState.SUMMARY:
            if state.summary_spoken:
                state.fsm_state = FsmState.GOODBYE
                return Planner._prompt_for_state(state, turn_id, generation_id)
            state.summary_spoken = True
            return TurnProposal(
                **base,
                speech="Спасибо за разговор.",
                intent="summary",
            )

        if state.fsm_state == FsmState.GOODBYE:
            if not state.goodbye_confirmed:
                state.fsm_state = FsmState.FINAL_CLASSIFICATION
                state.goodbye_confirmed = True
                state.final_action_done = True
                state.bump_version()
            return TurnProposal(
                **base,
                speech=_GOODBYE_FINAL,
                intent="goodbye_final",
            )

        if state.fsm_state == FsmState.RED_SIGNAL:
            return TurnProposal(
                **base,
                speech=_RED_SAFETY_PROMPT,
                intent="red_confirm_safety",
            )

        if state.fsm_state == FsmState.CONFIRM_SITUATION:
            return TurnProposal(
                **base,
                speech=_RED_CLARIFY,
                intent="red_clarified",
            )

        if state.fsm_state == FsmState.FINAL_CLASSIFICATION:
            if state.call_finalized:
                return Planner._terminal_noop(state, turn_id, generation_id)
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
    def _arm_pending_slot(
        state: DialogueState,
        slot: str,
        question: str | None = None,
    ) -> None:
        state.pending_slot = slot
        state.pending_question = question or _SLOT_QUESTIONS[slot]
        state.pending_question_delivered = False

    @staticmethod
    def _next_open_slot(state: DialogueState) -> str | None:
        return next_open_slot(state.slots)

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
        base_question = state.pending_question or "Повторите, пожалуйста."
        speech = base_question
        intent = "repair_repeat"
        if state.fsm_state == FsmState.DAILY_CHECK:
            speech = f"Да, слышу. {base_question.rstrip('?')}?".replace("??", "?")
            if not speech.endswith("?"):
                speech = f"{speech}?"
        elif state.pending_slot:
            intent = f"repeat_{state.pending_slot}"
        elif state.fsm_state == FsmState.CHECK_CONSENT:
            speech = (
                "Вы согласны получать регулярные звонки от Амвера? "
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
            # Explicit farewell is enough — no double confirm (align with DialogueEngine).
            state.goodbye_count = 2
            state.closing_requested = True
        elif interp and interp.requests_goodbye:
            state.goodbye_count = 2
            state.closing_requested = True
        elif normalized in {
            "пока",
            "заканчиваем",
            "закончим",
            "давайте закончим",
            "закончим разговор",
            "хватит разговор",
            "хватит",
            "стоп",
        }:
            state.goodbye_count = 2
            state.closing_requested = True

        can_close = Planner._may_enter_closing_fsm(state)

        if state.goodbye_count >= 2 or (interp and interp.confirms_goodbye):
            state.goodbye_confirmed = True
            state.call_ended_early = bool(state.mandatory_remaining())
            state.awaiting_goodbye_confirm = False
            state.fsm_state = FsmState.FINAL_CLASSIFICATION
            state.final_action_done = True
            state.termination_reason = (
                TerminationReason.EARLY_GOODBYE
                if state.mandatory_remaining()
                else TerminationReason.COMPLETED
            )
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
