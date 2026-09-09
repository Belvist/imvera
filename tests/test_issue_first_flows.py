"""Conversation-level issue-first flows (ADR-015)."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.scenario_runner import ScenarioRunner

pytestmark = pytest.mark.dialogue_engine

_BACKGROUND_LADDER = ("check_mood", "check_sleep", "check_plans", "clarify_mood", "clarify_sleep", "clarify_plans")


def _runner() -> ScenarioRunner:
    return ScenarioRunner(call_id="flows", elder_display_name="Тест")


def _intents(r: ScenarioRunner) -> list[str]:
    return [e.intent for e in r.effects if hasattr(e, "intent")]


def _no_background_ladder_before(intents: list[str], marker: str) -> None:
    if marker not in intents:
        pytest.fail(f"marker intent {marker!r} not in {intents}")
    idx = intents.index(marker)
    prefix = intents[:idx]
    for bad in _BACKGROUND_LADDER:
        assert bad not in prefix, f"{bad} before {marker}: {prefix}"


def test_flow_c_all_good_to_important_to_share() -> None:
    r = _runner()
    r.run([CallStarted(), "Всё хорошо", "Нет"])
    intents = _intents(r)
    _no_background_ladder_before(intents, "important_to_share")
    assert "important_to_share" in intents
    assert "summary" in intents


def test_flow_a_headache_improving_to_important_to_share() -> None:
    r = _runner()
    r.run([CallStarted(), "Голова болит и тошнит", "С утра, но сейчас уже лучше"])
    intents = _intents(r)
    _no_background_ladder_before(intents, "important_to_share")
    assert "important_to_share" in intents


def test_flow_sleep_to_important_to_share_no_mood_plans() -> None:
    r = _runner()
    r.run([CallStarted(), "Плохо спал, проснулся в четыре"])
    intents = _intents(r)
    _no_background_ladder_before(intents, "important_to_share")
    assert "important_to_share" in intents


def test_flow_mixed_identity_knee_no_background_ladder() -> None:
    r = _runner()
    r.run(
        [
            CallStarted(),
            "Нормально.",
            "А вы кто?",
            "Колено ноет.",
            "Второй день",
            "Ничего",
        ]
    )
    intents = _intents(r)
    assert "answer_user_question" in intents
    assert any(i.startswith("episode_") for i in intents)
    assert not any(i in intents for i in _BACKGROUND_LADDER)


def test_compound_temporal_current_closes_both() -> None:
    r = _runner()
    r.run([CallStarted(), "Голова болит", "С утра, сейчас уже лучше"])
    ep = next(iter(r.state.issue_episodes.values()))
    assert ep.status == "resolved" or ep.known_attributes.get("current")


def test_compound_known_current_asks_only_temporal() -> None:
    from packages.dialogue_engine.state import EngineState, IssueEpisode
    from packages.dialogue_engine.semantic_kernel.information_gain import best_question_need

    ep = IssueEpisode(
        episode_id="ep-1",
        primary_label="головная боль",
        kind="symptom",
        known_attributes={"current": "ещё болит"},
    )
    state = EngineState(call_id="t")
    need = best_question_need(state, ep)
    assert need is not None
    assert need.attribute in ("duration", "onset")
    assert not need.is_compound


def test_compound_known_duration_no_temporal_reask() -> None:
    from packages.dialogue_engine.state import EngineState, IssueEpisode
    from packages.dialogue_engine.semantic_kernel.information_gain import best_question_need

    ep = IssueEpisode(
        episode_id="ep-1",
        primary_label="головная боль",
        kind="symptom",
        known_attributes={"duration": "с утра", "onset": "с утра"},
    )
    state = EngineState(call_id="t")
    need = best_question_need(state, ep)
    assert need is None or need.attribute not in ("duration", "onset")
