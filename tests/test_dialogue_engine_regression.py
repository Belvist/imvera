"""Regression tests for DialogueEngine — fs-f0daadb9 class of bugs."""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue.interpretation import interpret_user_turn
from packages.dialogue.planner import Planner
from packages.dialogue.state import DialogueState
from packages.dialogue_engine.events import CallStarted, PlayoutCancelled
from packages.dialogue_engine.fast_interpreter import fast_interpret, fast_interpret_semantic
from packages.dialogue_engine.policy import mark_question_delivered, reserve_question
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.state import EngineState

pytestmark = pytest.mark.dialogue_engine


def _runner() -> ScenarioRunner:
    return ScenarioRunner(call_id="fs-regression", elder_display_name="Даниил")


def test_opening_never_replays_after_first_user_turn() -> None:
    r = _runner()
    result = r.run(
        [
            CallStarted(),
            "Хорошо себя чувствую.",
        ]
    )
    assert result.opening_count == 1
    assert result.state.first_user_turn_received
    assert result.state.slots["wellness"] == SlotStatus.FILLED
    assert not result.partial_close
    intents = [e.intent for e in result.speak_effects]
    assert intents.count("opening_wellness") == 1


def test_reserved_attempt_does_not_count_before_playout() -> None:
    state = EngineState(call_id="t", elder_display_name="Даниил")
    state, effects = reduce(state, CallStarted())
    assert effects
    speak = effects[0]
    goal = state.ensure_goal("wellness")
    assert goal.delivered_attempts == 0
    assert goal.reserved_question_id == speak.question_id


def test_cancelled_question_releases_reservation() -> None:
    state = EngineState(call_id="t", elder_display_name="Даниил")
    state, effects = reduce(state, CallStarted())
    speak = effects[0]
    state, _ = reduce(
        state,
        PlayoutCancelled(generation=speak.generation, question_id=speak.question_id),
    )
    goal = state.ensure_goal("wellness")
    assert goal.reserved_question_id is None
    assert goal.delivered_attempts == 0


def test_repair_request_does_not_consume_attempt() -> None:
    r = _runner()
    result = r.run(
        [
            CallStarted(),
            "Хорошо себя чувствую.",
            "Алло, ты меня слышишь?",
        ]
    )
    mood_goal = result.state.ensure_goal("mood")
    assert mood_goal.delivered_attempts <= 1
    assert not result.partial_close
    repair = [e for e in result.speak_effects if e.intent == "repair_repeat"]
    assert repair, "expected repair_repeat after алло"


def test_mood_accepts_contextual_positive_answer() -> None:
    interp, confident = fast_interpret("Хорошо себя чувствую.", answer_slot="mood")
    assert confident
    assert interp.fact_candidates
    assert interp.fact_candidates[0].field == "mood"


def test_wellness_then_mood_transition() -> None:
    r = _runner()
    result = r.run(
        [
            CallStarted(),
            "Хорошо себя чувствую.",
            "Нет.",
        ]
    )
    assert result.state.slots["wellness"] == SlotStatus.FILLED
    assert result.state.slots["mood"] == SlotStatus.OPEN
    intents = [e.intent for e in result.speak_effects]
    assert "important_to_share" in intents
    assert not result.partial_close


def test_slow_interpret_cannot_replay_opening() -> None:
    r = ScenarioRunner(
        call_id="slow-interpret",
        elder_display_name="Даниил",
        interpret_delay_s=0.01,
    )
    result = r.run(
        [
            CallStarted(),
            "Хорошо себя чувствую.",
        ]
    )
    assert result.opening_count == 1
    assert result.state.slots["wellness"] == SlotStatus.FILLED


def test_fs_f0daadb9_trace_sequence() -> None:
    """Reproduce fs-f0daadb9 utterances — must not partial_unresolved_close."""
    r = _runner()
    result = r.run(
        [
            CallStarted(),
            "Привет. Чувствую себя хорошо.",
            "Алло, ты",
            "Хорошо себя чувствую.",
        ]
    )
    assert not result.partial_close
    assert result.state.slots["wellness"] == SlotStatus.FILLED
    intents = [e.intent for e in result.speak_effects]
    assert "repair_repeat" in intents
    assert "check_mood" not in intents
    assert intents.count("opening_wellness") == 1


def test_fs_f0daadb9_delayed_interpret_stays_stable() -> None:
    """Prod trace had ~10s stale LLM; short delay proves revision guard (see interpret_delay_s)."""
    r = ScenarioRunner(
        call_id="fs-f0daadb9",
        elder_display_name="Даниил",
        interpret_delay_s=0.05,
    )
    result = r.run(
        [
            CallStarted(),
            "Хорошо себя чувствую.",
            "Алло, слышишь?",
            "Хорошее.",
        ]
    )
    assert result.opening_count == 1
    assert not result.partial_close
    # "Хорошее." may cover mood from free speech; must not force mood ladder or partial-close.
    assert "check_mood" not in [e.intent for e in result.speak_effects]
    assert "repair_repeat" in [e.intent for e in result.speak_effects]


def test_planner_stale_reservation_does_not_close_mood() -> None:
    state = DialogueState(call_id="t", elder_display_name="Даниил", family_id="f")
    Planner._begin_direct_daily_check(state)
    Planner._plan_opening_wellness(state, 1, "g-open")
    Planner.mark_question_delivered(state, "g-open")

    t1 = "Привет. Чувствую себя хорошо."
    i1 = interpret_user_turn(state, t1)
    p1 = Planner.plan_after_user(state, t1, "g-mood", 2, i1)
    assert p1.intent == "check_mood"
    assert state.get_goal("mood").reserved_attempt_id == "g-mood"

    t2 = "Алло, ты"
    i2 = interpret_user_turn(state, t2)
    p2 = Planner.plan_after_user(state, t2, "g-repair", 3, i2)
    assert p2.intent in ("check_mood", "clarify_mood")
    assert not state.is_terminal()
    assert not state.call_ended_early


def test_mark_question_delivered_increments_only_after_playout() -> None:
    state = EngineState(call_id="t", elder_display_name="Даниил")
    reserve_question(state, "mood", "q-1")
    assert state.ensure_goal("mood").delivered_attempts == 0
    mark_question_delivered(state, "mood", "q-1")
    assert state.ensure_goal("mood").delivered_attempts == 1


def test_fast_interpreter_latency_class() -> None:
    """Fast path must resolve common answers without LLM."""
    samples = [
        "хорошо",
        "нормально",
        "Хорошо себя чувствую",
        "Алло",
        "плохо",
    ]
    for text in samples:
        _interp, confident = fast_interpret(text, answer_slot="wellness")
        assert confident, f"expected fast path for: {text}"


def test_negative_wellness_gets_empathetic_ack() -> None:
    r = _runner()
    result = r.run([CallStarted(), "мне плохо"])
    assert result.state.slots["wellness"] == SlotStatus.FILLED
    intents = [e.intent for e in result.speak_effects]
    assert "probe_concern" in intents
    probe = next(e for e in result.speak_effects if e.intent == "probe_concern")
    # Warm reaction and the pending question now have separate canonical
    # components. Keep exact bank membership and verify the heard reaction.
    from packages.dialogue_engine import questions as _Q
    assert probe.question_text.strip() in _Q._PROBE_QUESTION_VARIANTS["concern"]
    assert probe.bridge_text.startswith("Мне жаль это слышать.")
    assert probe.text == f"{probe.bridge_text} {probe.question_text}"
    assert probe.text.count("?") == 1


def test_tebe_ploho_fast_path_negative_wellness() -> None:
    sem, confident = fast_interpret_semantic("Тебе плохо.", answer_slot="wellness")
    assert confident
    assert sem.polarity == "negative"
    assert sem.target_slot == "wellness"


def test_plans_none_fast_path_to_summary() -> None:
    r = _runner()
    result = r.run(
        [
            CallStarted(),
            "Хорошо.",
            "Нет.",
        ]
    )
    summary = [e for e in result.speak_effects if e.intent == "summary"]
    assert summary, "expected summary after important_to_share"
    text = summary[-1].text
    assert "спасибо" in text.lower()
    # Single-goodbye contract: farewell lives in goodbye_final only.
    assert "до свидания" not in text.lower()
    assert "Даниил" in text
    assert text != "Спасибо за разговор."


def test_plans_colloquial_none_phrase() -> None:
    sem, confident = fast_interpret_semantic(
        "Планов никаких нету.",
        answer_slot="plans",
    )
    assert confident
    assert sem.act.value == "answer"
    assert sem.target_slot == "plans"


@pytest.mark.parametrize(
    ("text", "slot"),
    [
        ("Великолепное настроение.", "mood"),
        ("Не очень, на самом деле, настроение у меня.", "mood"),
        ("Хорошо, спал.", "sleep"),
        ("Спало великолепно.", "sleep"),
        ("Планов нету на сегодня.", "plans"),
    ],
)
def test_live_colloquial_fast_path(text: str, slot: str) -> None:
    fsem, fok = fast_interpret_semantic(text, answer_slot=slot)
    assert fok, f"no fast path for {text!r} @ {slot}"
    assert fsem.act.value == "answer"


def test_full_daily_check_to_goodbye() -> None:
    r = _runner()
    result = r.run(
        [
            CallStarted(),
            "Хорошо.",
            "Нет.",
            "до свидания",
        ]
    )
    intents = [e.intent for e in result.speak_effects]
    assert "important_to_share" in intents
    assert "summary" in intents
    # Explicit farewell closes immediately — no double confirm.
    assert "goodbye_final" in intents
    assert "goodbye_confirm" not in intents
    assert result.state.call_closed
