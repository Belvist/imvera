"""Tests for wellness branching and cross-call follow-up."""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.check_path import prior_followup_question
from packages.dialogue_engine.state import CheckPath
from packages.dialogue_engine.events import CallStarted, PlayoutCompleted
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.state import EngineState
from packages.voice_perception.text_echo import is_repair_phrase, is_text_echo_of_bot


pytestmark = pytest.mark.dialogue_engine


def _runner() -> ScenarioRunner:
    return ScenarioRunner(call_id="check-path", elder_display_name="Даниил")


def test_echo_repair_kakoe_not_discarded() -> None:
    bot = "Мне жаль это слышать. А какое у вас сегодня настроение?"
    assert is_repair_phrase("Какое?")
    assert not is_text_echo_of_bot("Какое?", bot)


def test_wellness_good_full_ladder() -> None:
    result = _runner().run(
        [
            CallStarted(),
            "Хорошо себя чувствую.",
            "Нет.",
        ]
    )
    assert result.state.check_path == CheckPath.STANDARD
    intents = [e.intent for e in result.speak_effects]
    assert "check_mood" not in intents
    assert "important_to_share" in intents
    assert "summary" in intents


def test_wellness_good_mandatory_background_ladder() -> None:
    r = _runner()
    r.run([CallStarted()])
    r.state.mandatory_background_goals = True
    result = r.run(
        [
            "Хорошо себя чувствую.",
            "Ничего.",
            "Хорошее.",
            "Нормально спал.",
            "Пойду гулять.",
            "Ничего.",
        ]
    )
    intents = [e.intent for e in result.speak_effects]
    assert "important_to_share" in intents
    assert "check_mood" in intents
    assert "check_sleep" in intents
    assert "check_plans" in intents
    assert result.state.slots["plans"] == SlotStatus.FILLED


def test_wellness_bad_probes_then_mood() -> None:
    result = _runner().run(
        [
            CallStarted(),
            "Я чувствую себя плохо",
            "Болит голова",
            "Уже второй день",
            "Плохое настроение",
            "Плохо спал",
            "Дома посижу",
        ]
    )
    assert result.state.check_path == CheckPath.NEGATIVE_PROBE
    assert result.state.wellness_concern == "Болит голова"
    assert result.state.wellness_duration == "Уже второй день"
    intents = [e.intent for e in result.speak_effects]
    assert "probe_concern" in intents
    assert "probe_duration" in intents
    assert "summary" in intents


def test_wellness_bad_with_symptoms_skips_probe_concern() -> None:
    """Regression fs-3238b70a: do not re-ask «что беспокоит» after detailed wellness."""
    result = _runner().run(
        [
            CallStarted(),
            "Чувствую себя плохо, самочувствие плохое, голова кружится, всё болит.",
            "Продолжительное время.",
            "Не очень, на самом деле, настроение у меня.",
            "Плохо спал. Ну так, хорошо. Спал хорошо.",
            "Планов нету на сегодня.",
        ]
    )
    intents = [e.intent for e in result.speak_effects]
    assert "probe_concern" not in intents
    # Legacy probe_duration replaced by IssueEpisode attribute questions when symptoms named.
    assert "probe_duration" in intents or any(i.startswith("episode_") for i in intents)
    assert result.state.wellness_concern.startswith("Чувствую себя плохо")


def test_wellness_urgent_skips_to_close() -> None:
    result = _runner().run(
        [
            CallStarted(),
            "Мне очень плохо, вызывайте скорую",
        ]
    )
    assert result.state.check_path == CheckPath.URGENT
    assert result.state.call_closed
    intents = [e.intent for e in result.speak_effects]
    assert "urgent_close" in intents
    assert "check_mood" not in intents


def test_wellness_pain_short_path_to_plans() -> None:
    result = _runner().run(
        [
            CallStarted(),
            "Нормально, но болит голова",
            "Ночью тоже болело",
            "Ничего не буду делать",
        ]
    )
    intents = [e.intent for e in result.speak_effects]
    headache_ep = next(
        (
            ep
            for ep in result.state.issue_episodes.values()
            if "голов" in ep.primary_label.lower()
        ),
        None,
    )
    if headache_ep is not None:
        # Canonical IssueEpisode flow replaces legacy pain_short probe ladder.
        assert any(i.startswith("episode_") for i in intents)
        assert result.state.slots["plans"] == SlotStatus.FILLED
        return
    assert result.state.check_path == CheckPath.PAIN_SHORT
    assert result.state.slots["mood"] == SlotStatus.OPEN
    assert "mood" in result.state.skipped_slots
    assert "probe_pain_night" in intents
    assert "check_plans" in intents
    assert "check_mood" not in intents


def test_plans_colloquial_sidi_doma() -> None:
    from packages.dialogue_engine.fast_interpreter import fast_interpret_semantic
    from packages.dialogue_engine.semantic import SemanticAct

    sem, ok = fast_interpret_semantic(
        "А сидеть дома, ничего не делать",
        answer_slot="plans",
    )
    assert ok
    assert sem.act == SemanticAct.ANSWER
    assert sem.target_slot == "plans"


def test_prior_followup_from_memory() -> None:
    store = InMemoryCallRecordStore()
    family_id = "fam-memory"
    store.ensure_call("call-prev", family_id)
    from packages.contracts.core import CallResultSnapshot
    from packages.contracts.enums import FsmState

    store.finalize_call(
        CallResultSnapshot(
            call_id="call-prev",
            family_id=family_id,
            fsm_state=FsmState.FINAL_CLASSIFICATION,
            call_ended=True,
            metadata={"wellness_concern": "болела голова"},
        )
    )
    session = CallSession(
        call_id="call-next",
        family_id=family_id,
        store=store,
        elder_display_name="Даниил",
    )
    opening = session.start().validated.speech
    assert "голов" in opening.lower()

    assert prior_followup_question({"wellness_concern": "болела голова"})


def test_kakoe_repair_on_mood() -> None:
    from packages.dialogue_engine.context import InterpretContext
    from packages.dialogue_engine.contextual_interpreter import contextual_interpret
    from packages.dialogue_engine.events import UserTurnReceived
    from packages.dialogue_engine.fast_interpreter import fast_interpret_semantic
    from packages.dialogue_engine.semantic import SemanticAct

    state = EngineState(call_id="t", elder_display_name="Даниил")
    state, effects = reduce(state, CallStarted())
    state, _ = reduce(
        state,
        PlayoutCompleted(
            generation=effects[0].generation,
            question_id=effects[0].question_id,
        ),
    )
    sem_well, _ = fast_interpret_semantic("Плохо", answer_slot="wellness")
    state, effects = reduce(
        state,
        UserTurnReceived(turn_id="u-1", text="Плохо", semantic=sem_well),
    )
    state, _ = reduce(
        state,
        PlayoutCompleted(
            generation=effects[0].generation,
            question_id=effects[0].question_id,
        ),
    )
    ctx = InterpretContext.from_engine_state(state)
    sem, confident = contextual_interpret("Какое?", ctx)
    assert confident
    assert sem.act == SemanticAct.REPAIR_REQUEST
