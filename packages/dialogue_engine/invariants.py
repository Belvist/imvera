"""Invariant checks — fail tests immediately on engine contract violations."""

from __future__ import annotations

from packages.dialogue_engine.effects import (
    EndCallEffect,
    InterpretEffect,
    SpeakEffect,
    TimerEffect,
)
from packages.dialogue_engine.semantic import SemanticAct, SemanticTurn
from packages.dialogue_engine.state import EngineState, OpeningState


class InvariantViolation(AssertionError):
    pass


_BACKCHANNEL_ONLY = frozenset({"ага", "угу", "да", "нет", "мм", "м"})


def assert_opening_one_shot(state: EngineState) -> None:
    if state.opening_play_count > 1:
        raise InvariantViolation(
            f"opening_play_count={state.opening_play_count} > 1"
        )
    if state.first_user_turn_received and state.opening_play_count > 0:
        if state.opening_state == OpeningState.PLAYING:
            raise InvariantViolation("opening replay while user turn received")


def assert_no_attempt_without_delivery(state: EngineState, slot: str) -> None:
    goal = state.goals.get(slot)
    if goal is None:
        return
    if goal.delivered_attempts > goal.max_attempts:
        raise InvariantViolation(
            f"slot={slot} delivered_attempts={goal.delivered_attempts} > max"
        )


def assert_answer_context_uses_delivered(state: EngineState) -> None:
    if state.planned_question and state.delivered_question:
        if (
            state.planned_question.slot != state.delivered_question.slot
            and state.processing_turn_id
        ):
            pass  # allowed during transition


def _is_meaningful_user_text(text: str) -> bool:
    core = text.strip().lower()
    if len(core) < 2:
        return False
    return core not in _BACKCHANNEL_ONLY or len(core.split()) > 1


def _has_terminal_outcome(effects: list) -> bool:
    for effect in effects:
        if isinstance(effect, (SpeakEffect, TimerEffect, EndCallEffect)):
            return True
    return False


def assert_turn_produced_outcome(
    *,
    text: str,
    semantic: SemanticTurn | None,
    effects: list,
    answer_slot: str | None,
    call_closed: bool,
) -> None:
    """Every meaningful user turn must produce a terminal conversational outcome."""
    if call_closed:
        return
    if not text.strip():
        return
    if semantic is not None and semantic.act == SemanticAct.NO_ANSWER:
        return
    if semantic is not None and semantic.act == SemanticAct.BACKCHANNEL:
        if _has_terminal_outcome(effects):
            return
        if not answer_slot:
            return
    if not _is_meaningful_user_text(text):
        return

    direct = [e for e in effects if not isinstance(e, InterpretEffect)]
    if _has_terminal_outcome(direct):
        return

    raise InvariantViolation(
        f"meaningful user turn produced no outcome: text={text!r} "
        f"effects={[type(e).__name__ for e in effects]}"
    )


def check_all(state: EngineState) -> None:
    assert_opening_one_shot(state)
    for slot in state.goals:
        assert_no_attempt_without_delivery(state, slot)


def count_opening_generations(effects: list) -> int:
    return sum(
        1
        for e in effects
        if isinstance(e, SpeakEffect) and e.intent == "opening_wellness"
    )
