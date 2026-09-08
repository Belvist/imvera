"""Live-call regression fs-592f4ea0 — topic correctness (state + intents)."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner
from packages.dialogue_engine.state import TopicResolution
from packages.dialogue_engine.topic_tracker import TopicFamily

pytestmark = pytest.mark.dialogue_engine


def _runner() -> ScenarioRunner:
    return ScenarioRunner(call_id="fs-592f4ea0", elder_display_name="Даниил")


def test_fs_592f4ea0_sleep_then_mixed_turn_then_improving_abdominal() -> None:
    runner = _runner()
    result = runner.run([CallStarted(), "Плохо спал."])
    intents = [e.intent for e in result.speak_effects]
    assert "probe_concern" not in intents
    assert "topic_sleep_pattern" in intents

    result = runner.run(["Проснулся в 4, не мог заснуть, живот болел."])
    state = result.state
    assert state.active_topic == TopicFamily.SLEEP
    assert "quality" in state.topic_dimensions.get(TopicFamily.SLEEP, [])
    assert "pattern" in state.topic_dimensions.get(TopicFamily.SLEEP, [])
    assert TopicFamily.ABDOMINAL_PAIN in state.topic_evidence
    assert TopicFamily.ABDOMINAL_PAIN in state.pending_topics

    result = runner.run(["Усталость есть."])
    state = result.state
    assert state.slots.get("sleep") is not None or state.active_topic != TopicFamily.SLEEP

    result = runner.run(["Сейчас живот почти не болит."])
    state = result.state
    intents = [e.intent for e in result.speak_effects]
    assert state.topic_resolution.get(TopicFamily.ABDOMINAL_PAIN) == TopicResolution.IMPROVING
    assert "topic_abdominal_pain_onset" not in intents

    result = runner.run(["Хорошее настроение.", "Планов нет."])
    intents = [e.intent for e in result.speak_effects]
    assert "summary" in intents
