"""Dead uplink (zero PCM frames) gets a mic check, not reprompt/close."""

from __future__ import annotations

import pytest

from packages.contracts.enums import FsmState
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.events import TimerExpired
from packages.dialogue_engine.state import Question, QuestionPhase

pytestmark = pytest.mark.dialogue_engine

MEDS_Q = "Есть ли у вас лекарства, которые вы обычно принимаете?"


def _engine_with_delivered_meds() -> DialogueEngine:
    engine = DialogueEngine(call_id="miccheck", elder_display_name="Тест")
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
    engine.state.ensure_goal("background_medication").delivered_attempts = 1
    return engine


def _fire(engine: DialogueEngine, uplink_frames=None):
    from packages.dialogue_engine.reducer import reduce

    return reduce(
        engine.state,
        TimerExpired(
            timer_id="wait-background_medication",
            revision=engine.state.revision,
            uplink_frames=uplink_frames,
        ),
    )


def test_dead_uplink_speaks_mic_check_once() -> None:
    engine = _engine_with_delivered_meds()
    state, effects = _fire(engine, uplink_frames=0)
    assert not state.call_closed
    assert state.mic_check_spoken
    speaks = [e for e in effects if getattr(e, "kind", "") == "speak"]
    assert len(speaks) == 1
    assert speaks[0].text.startswith("Вас не слышно."), speaks[0].text
    assert speaks[0].intent == "mic_check"
    # Question still pending + timer re-armed (call must not hang open).
    assert state.waiting_on_slot == "background_medication"
    from packages.dialogue_engine.effects import TimerEffect

    assert any(isinstance(e, TimerEffect) for e in effects)
    # Cap untouched: nobody answered anything.
    assert state.ensure_goal("background_medication").delivered_attempts == 1
    assert state.silence_reprompts == 0


def test_second_dead_silence_falls_through() -> None:
    engine = _engine_with_delivered_meds()
    state, _ = _fire(engine, uplink_frames=0)
    engine.state = state
    engine.state.waiting_on_slot = "background_medication"
    state2, effects2 = _fire(engine, uplink_frames=0)
    texts = [getattr(e, "text", "") for e in effects2]
    assert not any("не слышно" in t for t in texts)


def test_unknown_uplink_keeps_old_path() -> None:
    engine = _engine_with_delivered_meds()
    state, effects = _fire(engine, uplink_frames=None)
    assert not state.mic_check_spoken
    speaks = [e for e in effects if getattr(e, "kind", "") == "speak"]
    assert any(t.startswith("Алло.") for t in [getattr(e, "text", "") for e in speaks])
