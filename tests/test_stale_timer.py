"""Stale wait timers must die quietly, never resurrect old questions (P0 G-18)."""

from __future__ import annotations

import pytest

from packages.contracts.enums import FsmState, SlotStatus
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.events import TimerExpired
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.state import Question, QuestionPhase

pytestmark = pytest.mark.dialogue_engine


def _engine() -> DialogueEngine:
    engine = DialogueEngine(call_id="stale-timer", elder_display_name="Тест")
    engine.start()
    engine.state.fsm_state = FsmState.DAILY_CHECK
    return engine


def _expired(engine: DialogueEngine, timer_id: str):
    return reduce(
        engine.state,
        TimerExpired(timer_id=timer_id, revision=engine.state.revision),
    )


def test_moved_on_timer_dies_quietly() -> None:
    engine = _engine()
    engine.state.waiting_on_slot = None
    engine.state.delivered_question = Question(
        question_id="g-mood",
        slot="mood",
        text="А какое у вас сегодня настроение?",
        phase=QuestionPhase.DELIVERED,
        intent="check_mood",
    )
    state, effects = _expired(engine, "wait-wellness")
    assert effects == [], effects


def test_filled_slot_timer_dies_quietly() -> None:
    engine = _engine()
    engine.state.waiting_on_slot = None
    engine.state.delivered_question = None
    engine.state.slots["wellness"] = SlotStatus.FILLED
    state, effects = _expired(engine, "wait-wellness")
    assert effects == [], effects


def test_live_timer_still_reprompts() -> None:
    engine = _engine()
    engine.state.waiting_on_slot = "wellness"
    engine.state.delivered_question = Question(
        question_id="g-well",
        slot="wellness",
        text="Как вы себя чувствуете?",
        phase=QuestionPhase.DELIVERED,
        intent="check_wellness",
    )
    # Fresh attempt budget (reserve governs speaking, unrelated to staleness).
    # Simulate post-delivery state: reservation cleared by PlayoutCompleted.
    goal = engine.state.ensure_goal("wellness")
    goal.delivered_attempts = 0
    goal.reserved_question_id = None
    state, effects = _expired(engine, "wait-wellness")
    speaks = [e for e in effects if getattr(e, "kind", "") == "speak"]
    assert len(speaks) == 1


def test_stale_playing_does_not_block_close() -> None:
    from packages.dialogue_engine.reducer import _close_partial, _emit_speak

    engine = _engine()
    engine.state.fsm_state = FsmState.DAILY_CHECK
    state, _ = _emit_speak(
        engine.state,
        text="Как вы?",
        intent="check_wellness",
        slot="wellness",
        marks_question=True,
    )
    assert state.playing_question is not None
    # Playout died without started/completed events: close must proceed.
    closed, effects = _close_partial(state)
    assert closed.call_closed is True
    assert any(getattr(e, "kind", "") == "speak" for e in effects)


def test_live_playing_blocks_close() -> None:
    from packages.dialogue_engine.reducer import _close_partial, _emit_speak

    engine = _engine()
    engine.state.fsm_state = FsmState.DAILY_CHECK
    state, _ = _emit_speak(
        engine.state,
        text="Как вы?",
        intent="check_wellness",
        slot="wellness",
        marks_question=True,
    )
    assert state.playing_question is not None
    # Vera audibly speaking: close waits, no stall-silence contract broken.
    state.playing_question = state.playing_question.model_copy(
        update={"phase": QuestionPhase.PLAYING}
    )
    closed, effects = _close_partial(state)
    assert effects == []
    assert closed.call_closed is False
