"""Semantic scope validation — stale by meaning, not revision alone."""

from __future__ import annotations

from packages.contracts.enums import FsmState
from packages.dialogue_engine.effects import SpeakEffect, TimerEffect
from packages.dialogue_engine.state import EngineState


def speak_scope_for(
    *,
    intent: str,
    generation_id: str,
    slot: str | None,
    marks_question: bool,
) -> str:
    if intent == "summary":
        return f"summary:{generation_id}"
    if intent in ("goodbye_confirm", "goodbye_final", "partial_unresolved_close"):
        return f"closing:{generation_id}"
    if marks_question and slot:
        return f"question:{slot}:{generation_id}"
    return f"speak:{intent}:{generation_id}"


def timer_scope_for(*, timer_id: str, question_id: str = "") -> str:
    key = question_id or timer_id.removeprefix("wait-")
    return f"wait:{key}"


def speak_scope_active(effect: SpeakEffect, state: EngineState) -> bool:
    scope = effect.semantic_scope_id
    if not scope:
        return True
    if scope.startswith("question:"):
        parts = scope.split(":", 2)
        if len(parts) < 3:
            return True
        _kind, slot, qid = parts[0], parts[1], parts[2]
        dq = state.delivered_question
        pq = state.playing_question
        if dq and dq.question_id == qid:
            return True
        if pq and pq.question_id == qid:
            return True
        if dq and dq.slot == slot and state.waiting_on_slot == slot:
            return True
        return False
    if scope.startswith("summary:"):
        return (
            (state.summary_spoken or state.fsm_state == FsmState.SUMMARY)
            and not state.goodbye_confirmed
        )
    if scope.startswith("closing:"):
        if effect.intent == "goodbye_confirm":
            return state.awaiting_goodbye_confirm or state.fsm_state == FsmState.GOODBYE
        if effect.intent == "goodbye_final":
            return state.goodbye_confirmed or state.call_closed
        return state.call_closed
    return True


def timer_scope_active(effect: TimerEffect, state: EngineState) -> bool:
    scope = effect.semantic_scope_id
    if not scope:
        slot = effect.timer_id.removeprefix("wait-")
        return state.waiting_on_slot == slot or state.answer_context_slot() == slot
    if scope.startswith("wait:"):
        key = scope.removeprefix("wait:")
        if state.waiting_on_slot == key:
            return True
        dq = state.delivered_question
        if dq and dq.question_id == key:
            return True
        if dq and dq.slot == key and state.waiting_on_slot == key:
            return True
    return False
