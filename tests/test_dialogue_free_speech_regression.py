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
    assert ep.known_attributes.get("onset") == "С 10 утра."
    intents = [e.intent for e in result.speak_effects]
    assert "episode_headache_severity" in intents
    assert "episode_headache_onset" not in intents

    result = runner.run(["Сильная."])
    ep = _headache_episode(result.state)
    assert ep is not None
    assert ep.known_attributes.get("severity") == "Сильная."
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
    intents = [e.intent for e in result.speak_effects]
    assert "topic_sleep_pattern" in intents or any(
        "ночью" in e.text.lower() for e in result.speak_effects
    )


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
