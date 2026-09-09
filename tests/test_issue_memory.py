"""Issue episode memory ingest."""

from __future__ import annotations

from packages.dialogue_engine.issue_memory import has_abdominal_episode, ingest_rich_turn
from packages.dialogue_engine.state import EngineState
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text


def test_headache_nausea_single_episode_no_abdominal() -> None:
    state = EngineState(call_id="t", elder_display_name="Тест")
    turn = build_rich_turn_from_text(
        "Голова болит и тошнит.",
        utterance_id="u-1",
    )
    ingest_rich_turn(state, turn)
    assert state.active_episode_id is not None
    ep = state.issue_episodes[state.active_episode_id]
    assert "голов" in ep.primary_label.lower()
    assert any(m.label == "тошнота" for m in ep.mentions)
    assert not has_abdominal_episode(state)


def test_two_independent_episodes() -> None:
    state = EngineState(call_id="t", elder_display_name="Тест")
    turn = build_rich_turn_from_text(
        "Голова болит, ещё живот ноет.",
        utterance_id="u-1",
    )
    ingest_rich_turn(state, turn)
    assert state.active_episode_id is not None
    assert state.pending_episode_ids
    assert has_abdominal_episode(state)


def test_generic_ear_issue() -> None:
    state = EngineState(call_id="t", elder_display_name="Тест")
    turn = build_rich_turn_from_text("Ухо заложило.", utterance_id="u-1")
    ingest_rich_turn(state, turn)
    ep = state.issue_episodes[state.active_episode_id]
    assert "ухо" in ep.primary_label.lower()
