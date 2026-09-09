"""Free-speech regression — not scripted fs-592."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.issue_memory import get_active_episode, has_abdominal_episode
from packages.dialogue_engine.issue_mention_extract import should_use_rich_turn
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.topic_tracker import is_topic_slot


def _headache_episode(state):
    for ep in state.issue_episodes.values():
        if "голов" in ep.primary_label.lower():
            return ep
    return get_active_episode(state)

pytestmark = pytest.mark.dialogue_engine


def _runner() -> ScenarioRunner:
    return ScenarioRunner(call_id="free-speech", elder_display_name="Тест")


def test_headache_nausea_no_abdominal_question() -> None:
    runner = _runner()
    runner.run([CallStarted()])
    result = runner.run(
        ["Состояние не очень, голова болит и тошнит."],
    )
    intents = [e.intent for e in result.speak_effects]
    assert "topic_abdominal_pain_current" not in intents
    assert not has_abdominal_episode(result.state)
    assert any(
        "headache" in i or "голов" in e.text.lower()
        for i, e in zip(intents, result.speak_effects, strict=False)
    )

    ep = _headache_episode(result.state)
    assert ep is not None
    assert ep.known_attributes.get("onset") is None

    result = runner.run(["С 10 утра."])
    ep = _headache_episode(result.state)
    assert ep is not None
    # QuestionNeed: temporal answer stored as actual type (duration ≠ onset); no fake mapping.
    temporal = ep.known_attributes.get("duration") or ep.known_attributes.get("onset") or ""
    assert "10" in temporal
    intents = [e.intent for e in result.speak_effects]
    assert "episode_headache_severity" in intents
    assert "episode_headache_onset" not in intents

    result = runner.run(["Сильная."])
    ep = _headache_episode(result.state)
    assert ep is not None
    assert (ep.known_attributes.get("severity") or "").startswith("Сильная")
    intents = [e.intent for e in result.speak_effects]
    texts = " ".join(e.text.lower() for e in result.speak_effects)
    assert "topic_abdominal_pain_current" not in intents
    assert "живот" not in texts
    assert "episode_headache_onset" not in intents


def test_user_question_then_resume() -> None:
    runner = _runner()
    runner.run([CallStarted(), "Плохо спал."])
    result = runner.run(["А вы кто вообще?"])
    texts = " ".join(e.text for e in result.speak_effects)
    assert "Вера" in texts
    assert result.state.suspended_obligation is not None

    result = runner.run(["Хорошо."])
    intents = [e.intent for e in runner.effects if hasattr(e, "intent")]
    assert intents
    assert any(
        i in intents
        for i in (
            "important_to_share",
            "important_to_share_followup",
            "topic_sleep",
            "check_sleep",
        )
    ) or any(i.startswith("episode_") for i in intents)


def test_headache_resolved_skips_severity_and_extra_episodes() -> None:
    """Live regression: «боль прошла» must close episode, not re-ask severity."""
    runner = _runner()
    runner.run([CallStarted(), "Голова болит и тошнит."])
    result = runner.run(["Со вчерашнего дня."])
    intents = [e.intent for e in result.speak_effects]
    assert "episode_headache_duration" not in intents
    assert len(result.state.issue_episodes) == 1

    result = runner.run(["Всё, боль прошла."])
    intents = [e.intent for e in result.speak_effects]
    texts = " ".join(e.text.lower() for e in result.speak_effects)
    assert "episode_headache_severity" not in intents
    assert "сильная" not in texts and "терпимая" not in texts
    ep = _headache_episode(result.state)
    assert ep is not None
    assert ep.status == "resolved"
    assert result.state.active_episode_id is None


def test_abdominal_resolved_single_episode_preserves_onset() -> None:
    runner = _runner()
    runner.run([CallStarted(), "Болит живот.", "С утра."])
    assert len(runner.state.issue_episodes) == 1
    ep_id = next(iter(runner.state.issue_episodes))
    result = runner.run(["Сейчас уже не болит."])
    ep = result.state.issue_episodes[ep_id]
    assert ep.status == "resolved"
    assert (ep.known_attributes.get("onset") or "").startswith("С утра")
    assert ep.known_attributes.get("current") == "resolved"
    intents = [e.intent for e in result.speak_effects]
    assert "episode_headache_severity" not in intents


def test_headache_severity_completes_episode() -> None:
    runner = _runner()
    runner.run([CallStarted(), "Голова болит.", "С утра."])
    result = runner.run(["Терпимая."])
    ep = _headache_episode(result.state)
    assert ep is not None
    assert ep.status == "resolved"
    assert ep.known_attributes.get("severity", "").startswith("Терпимая")


def test_correction_not_dumb_repeat() -> None:
    runner = _runner()
    runner.run([CallStarted(), "Живот болит."])
    result = runner.run(["Я же говорил, живот болит."])
    texts = " ".join(e.text.lower() for e in result.speak_effects)
    assert "говорили" in texts


def test_rich_required_inside_topic_slot() -> None:
    assert should_use_rich_turn(
        "Не знаю, ещё грудь давит и дышать тяжело.",
        "topic_headache_onset",
        is_topic_slot_fn=is_topic_slot,
    )


def test_backchannel_not_rich() -> None:
    from packages.dialogue_engine.issue_mention_extract import requires_rich_interpretation

    assert requires_rich_interpretation("Голова болит и тошнит.")
    assert not requires_rich_interpretation("угу")
