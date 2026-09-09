"""Contextual interpreter — same phrase, different delivered-question meaning."""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.context import InterpretContext
from packages.dialogue_engine.contextual_interpreter import contextual_interpret, interpret_structured
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.semantic import SemanticAct
from packages.dialogue_engine.state import EngineState, Question, QuestionPhase


pytestmark = pytest.mark.dialogue_engine


def _ctx(answer_slot: str | None, **kwargs) -> InterpretContext:
    state = EngineState(call_id="ctx", elder_display_name="Даниил")
    if answer_slot:
        state.delivered_question = Question(
            question_id="q-1",
            slot=answer_slot,
            text="?",
            phase=QuestionPhase.DELIVERED,
        )
    base = InterpretContext.from_engine_state(state)
    if kwargs:
        return InterpretContext(
            delivered_question=kwargs.get("delivered_question", base.delivered_question),
            playing_question=kwargs.get("playing_question", base.playing_question),
            answer_slot=answer_slot,
            open_slots=kwargs.get("open_slots", base.open_slots),
            filled_slots=kwargs.get("filled_slots", base.filled_slots),
            fsm_state=kwargs.get("fsm_state", base.fsm_state),
            summary_spoken=kwargs.get("summary_spoken", False),
            awaiting_goodbye_confirm=kwargs.get("awaiting_goodbye_confirm", False),
        )
    return base


@pytest.mark.parametrize(
    ("slot", "expected_slots"),
    [
        ("wellness", {"wellness"}),
        ("mood", {"mood"}),
        ("sleep", {"sleep"}),
    ],
)
def test_horo_context_dependent_answer(slot: str, expected_slots: set[str]) -> None:
    sem, confident = contextual_interpret("Хорошо.", _ctx(slot))
    assert confident
    assert sem.act == SemanticAct.ANSWER
    assert set(sem.slots) == expected_slots or sem.target_slot in expected_slots


def test_horo_on_plans_is_backchannel_not_answer() -> None:
    sem, confident = contextual_interpret("Хорошо.", _ctx("plans"))
    assert confident
    assert sem.act == SemanticAct.BACKCHANNEL


def test_poydet_on_plans_is_backchannel() -> None:
    sem, confident = contextual_interpret("Пойдёт.", _ctx("plans"))
    assert confident
    assert sem.act == SemanticAct.BACKCHANNEL


def test_multi_slot_wellness_sleep_plans() -> None:
    from packages.dialogue_engine.events import CallStarted

    r = ScenarioRunner(call_id="multi", elder_display_name="Даниил")
    result = r.run(
        [
            CallStarted(),
            "Отлично, выспался прекрасно, сегодня пойду гулять с дочкой.",
        ]
    )
    assert result.state.slots["wellness"] == SlotStatus.FILLED
    assert result.state.slots["sleep"] == SlotStatus.FILLED
    assert result.state.slots["plans"] == SlotStatus.FILLED
    assert result.state.slots["mood"] == SlotStatus.OPEN
    mood_q = [e for e in result.speak_effects if e.intent == "check_mood"]
    assert mood_q
    assert "настроение" in mood_q[0].text.lower()
    assert not any(e.intent == "check_sleep" for e in result.speak_effects)
    assert not any(e.intent == "check_plans" for e in result.speak_effects)


def test_mixed_sentiment_wellness_and_mood() -> None:
    structured = interpret_structured(
        "Сам нормально, но настроение сегодня ужасное.",
        _ctx("wellness"),
    )
    assert "wellness" in structured.slots
    assert "mood" in structured.slots
    assert structured.slots["mood"].polarity == "negative"


def test_correction_normally_no_bad() -> None:
    sem, confident = contextual_interpret(
        "Нормально... хотя нет, сегодня плохо.",
        _ctx("wellness"),
    )
    assert confident
    assert sem.correction
    assert sem.slots["wellness"].polarity == "negative"


def test_bad_wellness_empathetic_ack() -> None:
    r = ScenarioRunner(call_id="bad", elder_display_name="Даниил")
    from packages.dialogue_engine.events import CallStarted

    r.run([CallStarted()])
    r.state.wellness_probes_enabled = False
    result = r.run(["мне плохо"])
    mood = [e for e in result.speak_effects if e.intent == "check_mood"]
    assert mood[0].text.startswith("Мне жаль это слышать.")


def test_multi_slot_bad_skips_sleep_and_plans_questions() -> None:
    from packages.dialogue_engine.events import CallStarted

    r = ScenarioRunner(call_id="bad-multi", elder_display_name="Даниил")
    r.run([CallStarted()])
    r.state.wellness_probes_enabled = False
    result = r.run(
        [
            "Плохо сегодня, почти не спал, планов никаких.",
        ]
    )
    assert result.state.slots["sleep"] == SlotStatus.FILLED
    assert result.state.slots["plans"] == SlotStatus.FILLED
    assert result.state.slots["mood"] == SlotStatus.OPEN
    assert not any(e.intent == "check_sleep" for e in result.speak_effects)
