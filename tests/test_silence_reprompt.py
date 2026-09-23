"""Silence is not an answer attempt: first timeout reprompts, never closes."""

from __future__ import annotations

import pytest

from packages.contracts.enums import FsmState
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.events import TimerExpired
from packages.dialogue_engine.state import Question, QuestionPhase

pytestmark = pytest.mark.dialogue_engine

MEDS_Q = "Есть ли у вас лекарства, которые вы обычно принимаете?"


def _engine_with_delivered_meds() -> DialogueEngine:
    engine = DialogueEngine(call_id="silence", elder_display_name="Тест")
    engine.start()
    engine.state.fsm_state = FsmState.DAILY_CHECK
    engine.state.delivered_question = Question(
        question_id="g-meds",
        slot="background_medication",
        text=MEDS_Q,
        phase=QuestionPhase.DELIVERED,
        intent="background_medication",
    )
    engine.state.waiting_on_slot = "background_medication"
    goal = engine.state.ensure_goal("background_medication")
    goal.delivered_attempts = 1
    return engine


def _fire_timer(engine: DialogueEngine):
    from packages.dialogue_engine.reducer import reduce

    return reduce(
        engine.state,
        TimerExpired(
            timer_id="wait-background_medication", revision=engine.state.revision
        ),
    )


def test_first_silence_reprompts_without_closing() -> None:
    engine = _engine_with_delivered_meds()
    state, effects = _fire_timer(engine)
    assert not state.call_closed
    speaks = [e for e in effects if getattr(e, "kind", "") == "speak"]
    assert len(speaks) == 1
    assert speaks[0].text == f"Алло. {MEDS_Q}"
    assert speaks[0].intent == "background_medication"
    assert state.silence_reprompts == 1
    # Cap refunded: the unanswered ask was not an attempt.
    assert state.ensure_goal("background_medication").delivered_attempts == 0


def test_second_silence_falls_through_to_normal_path() -> None:
    engine = _engine_with_delivered_meds()
    state, _ = _fire_timer(engine)
    engine.state = state
    engine.state.waiting_on_slot = "background_medication"
    # Simulate delivery of the reprompt (cap consumed again).
    engine.state.ensure_goal("background_medication").delivered_attempts = 1
    state2, effects2 = _fire_timer(engine)
    texts = [getattr(e, "text", "") for e in effects2]
    assert not any(t.startswith("Алло.") for t in texts)
    assert state2.silence_reprompts == 1
