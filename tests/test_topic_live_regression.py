"""Live-call regression fs-592f4ea0 — IssueEpisode + background ladder (canonical)."""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine


def _runner() -> ScenarioRunner:
    return ScenarioRunner(call_id="fs-592f4ea0", elder_display_name="Даниил")


def test_fs_592f4ea0_sleep_then_mixed_turn_then_improving_abdominal() -> None:
    """fs-592f4ea0: poor sleep + abdominal mention → IssueEpisode focus, then ladder."""
    runner = _runner()
    result = runner.run([CallStarted(), "Плохо спал."])
    intents = [e.intent for e in result.speak_effects]
    assert "probe_concern" not in intents
    # old transport: topic_sleep_pattern → canonical: sleep slot fill + mood ladder
    assert result.state.slots["sleep"] == SlotStatus.FILLED

    result = runner.run(["Проснулся в 4, не мог заснуть, живот болел."])
    state = result.state
    abdominal = next(
        (ep for ep in state.issue_episodes.values() if "живот" in ep.primary_label.lower()),
        None,
    )
    assert abdominal is not None
    assert state.active_episode_id == abdominal.episode_id
    assert any(i.startswith("episode_") for i in [e.intent for e in result.speak_effects])

    result = runner.run(["Усталость есть."])
    state = result.state
    assert state.slots["sleep"] == SlotStatus.FILLED
    assert state.active_episode_id == abdominal.episode_id

    result = runner.run(["Сейчас живот почти не болит."])
    state = result.state
    abdominal = state.issue_episodes[abdominal.episode_id]
    assert abdominal.known_attributes.get("current") is not None
    assert state.slots["mood"] == SlotStatus.OPEN

    result = runner.run(["Ничего."])
    intents = [e.intent for e in runner.effects if hasattr(e, "intent")]
    assert "important_to_share" in intents
    assert "summary" in intents
