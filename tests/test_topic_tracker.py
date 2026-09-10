"""Tests for topic-based dialogue (MVP adaptive layer port)."""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.state import EngineState
from packages.dialogue_engine.topic_tracker import (
    TopicFamily,
    detect_families,
    detect_families_in_clause,
    infer_dimensions,
    ingest_user_turn_topics,
    prime_topics,
)

pytestmark = pytest.mark.dialogue_engine


def _runner() -> ScenarioRunner:
    return ScenarioRunner(call_id="topic-test", elder_display_name="Даниил")


def test_detect_sleep_from_poor_sleep_phrase() -> None:
    assert TopicFamily.SLEEP in detect_families("Плохо спал.")


def test_multi_family_per_clause_abdominal_and_sleep() -> None:
    families = detect_families_in_clause("из-за живота плохо спал")
    assert TopicFamily.SLEEP in families
    assert TopicFamily.ABDOMINAL_PAIN in families


def test_multi_family_both_clauses() -> None:
    families = detect_families("Живот болел и плохо спал")
    assert TopicFamily.SLEEP in families
    assert TopicFamily.ABDOMINAL_PAIN in families


def test_infer_sleep_quality_not_pattern() -> None:
    dims = infer_dimensions(TopicFamily.SLEEP, "Плохо спал.")
    assert "quality" in dims
    assert "pattern" not in dims


def test_infer_sleep_pattern_from_wake_time() -> None:
    dims = infer_dimensions(
        TopicFamily.SLEEP,
        "Проснулся в четыре, потом долго не мог заснуть.",
    )
    assert "pattern" in dims


def test_infer_abdominal_current_when_improving() -> None:
    dims = infer_dimensions(
        TopicFamily.ABDOMINAL_PAIN,
        "Сейчас живот уже почти не болит, вроде прошло.",
    )
    assert "current" in dims


def test_prime_topics_sets_active_and_quality_only() -> None:
    state = EngineState(call_id="t1", elder_display_name="")
    prime_topics(state, "Плохо спал.")
    assert state.active_topic == TopicFamily.SLEEP
    assert "quality" in state.topic_dimensions.get(TopicFamily.SLEEP, [])
    assert "pattern" not in state.topic_dimensions.get(TopicFamily.SLEEP, [])


def test_ingest_mixed_turn_keeps_sleep_active_queues_abdominal() -> None:
    state = EngineState(call_id="t1", elder_display_name="")
    prime_topics(state, "Плохо спал.")
    ingest_user_turn_topics(state, "Проснулся в 4, не мог заснуть, живот болел")
    assert TopicFamily.SLEEP in state.topic_evidence
    assert TopicFamily.ABDOMINAL_PAIN in state.topic_evidence
    assert "pattern" in state.topic_dimensions.get(TopicFamily.SLEEP, [])
    assert TopicFamily.ABDOMINAL_PAIN in state.pending_topics
    assert state.active_topic == TopicFamily.SLEEP


def test_abdominal_onset_from_turn_context() -> None:
    state = EngineState(call_id="t1", elder_display_name="")
    ingest_user_turn_topics(state, "Проснулся в 4, живот болел")
    from packages.dialogue_engine.topic_tracker import dimensions_satisfied

    assert dimensions_satisfied(state, TopicFamily.ABDOMINAL_PAIN, "onset")


def test_limb_pain_not_duplicated_as_general_symptom() -> None:
    families = detect_families_in_clause("Нога болит.")
    assert TopicFamily.LIMB_PAIN in families
    assert TopicFamily.GENERAL_SYMPTOM not in families


def test_off_topic_answer_does_not_fill_asked_dimension() -> None:
    state = EngineState(call_id="t1", elder_display_name="")
    prime_topics(state, "Плохо спал.")
    state.topic_asked_dimension = "pattern"
    ingest_user_turn_topics(state, "А вы кто вообще?")
    assert "pattern" not in state.topic_dimensions.get(TopicFamily.SLEEP, [])


def test_headache_at_sleep_slot_starts_topic_not_clarify() -> None:
    """Background sleep slot + headache complaint → episode focus, not sleep clarify loop.

    Legacy transport expected topic_headache_*; canonical IssueEpisode flow replaces it.
    """
    result = _runner().run(
        [
            CallStarted(),
            "Хорошо себя чувствую.",
            "Хорошее настроение.",
            "Голова сильно болит.",
        ]
    )
    intents = [e.intent for e in result.speak_effects]
    assert "clarify_sleep" not in intents
    headache_ep = next(
        (
            ep
            for ep in result.state.issue_episodes.values()
            if "голов" in ep.primary_label.lower()
        ),
        None,
    )
    assert headache_ep is not None, "headache IssueEpisode must capture focus"
    assert result.state.active_episode_id == headache_ep.episode_id
    assert any(i.startswith("episode_") for i in intents)


def test_poor_sleep_at_wellness_starts_topic_not_probe() -> None:
    """Regression fs-592f4ea0: «плохо спал» at wellness → sleep addressed, not concern probe."""
    result = _runner().run(
        [
            CallStarted(),
            "Плохо спал.",
        ]
    )
    intents = [e.intent for e in result.speak_effects]
    assert "probe_concern" not in intents
    # old transport: topic_sleep_* → canonical: background sleep slot fill + ladder advance
    assert result.state.slots["sleep"] == SlotStatus.FILLED
    assert any(ep.kind == "sleep_problem" for ep in result.state.issue_episodes.values())


def test_sleep_topic_then_mood_ladder() -> None:
    # old transport: topic_sleep_* ladder → canonical: background goals + important_to_share → summary
    result = _runner().run(
        [
            CallStarted(),
            "Плохо спал.",
            "Хорошее настроение.",
            "Планов нет.",
            "Нет, больше ничего.",
        ]
    )
    intents = [e.intent for e in result.speak_effects]
    assert "important_to_share" in intents
    assert "summary" in intents
    assert result.state.slots["sleep"] == SlotStatus.FILLED
    # Free speech covers mood/plans when the elder states them — not a forced ladder.
    assert result.state.slots["mood"] == SlotStatus.FILLED
    assert result.state.slots["plans"] == SlotStatus.FILLED
    assert "check_mood" not in intents
    assert "check_plans" not in intents


def test_abdominal_in_probe_answer_switches_topic() -> None:
    """Issue named during generic probe must survive — not become bare duration."""
    result = _runner().run(
        [
            CallStarted(),
            "Чувствую себя плохо.",
            "Проснулся в четыре, живот немного побаливал.",
        ]
    )
    intents = [e.intent for e in result.speak_effects]
    texts = " ".join(e.text.lower() for e in result.speak_effects)
    has_abdominal_episode = any(
        ep.body_site == "живот" or "живот" in ep.primary_label.lower()
        for ep in result.state.issue_episodes.values()
    )
    assert has_abdominal_episode or any(
        i.startswith("topic_abdominal_pain_")
        or i.startswith("topic_sleep_")
        or (i.startswith("episode_") and "живот" in texts)
        for i in intents
    )
    # Must not drop the named concern into orphan probe_duration.
    if intents and intents[-1] == "probe_duration":
        assert has_abdominal_episode


def test_never_silent_on_sleep_complaint() -> None:
    """Regression fs-641ab72d: complaint at sleep question must get Vera response."""
    result = _runner().run(
        [
            CallStarted(),
            "Хорошо себя чувствую.",
            "Хорошее.",
            "Нормально спал.",
            "А-а, плохо болело сердце. Я же говорил же.",
        ]
    )
    assert result.speak_effects, "every meaningful turn must produce Vera speech"
