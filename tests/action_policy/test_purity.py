from __future__ import annotations

import copy

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.snapshot import TurnContextView, build_policy_snapshot
from packages.dialogue_engine.state import BackgroundGoalCoverage, EngineState, IssueEpisode


def _state() -> EngineState:
    state = EngineState(call_id="purity")
    ep = IssueEpisode(
        episode_id="ep-1",
        primary_label="generic issue",
        kind="symptom",
        known_attributes={"onset": "yesterday"},
    )
    state.issue_episodes[ep.episode_id] = ep
    state.active_episode_id = ep.episode_id
    state.slots["wellness"] = SlotStatus.FILLED
    state.background_goal_status["wellness"] = BackgroundGoalCoverage.ANSWERED.value
    return state


def test_choose_does_not_mutate_engine_or_snapshot() -> None:
    state = _state()
    snapshot = build_policy_snapshot(state)
    state_before = copy.deepcopy(state.model_dump(mode="python"))
    snapshot_before = copy.deepcopy(snapshot)

    decision = choose(snapshot, TurnContextView(raw_text="ok"))

    assert decision.chosen is not None
    assert state.model_dump(mode="python") == state_before
    assert snapshot == snapshot_before


def test_repeated_calls_are_deterministic_and_pure() -> None:
    state = _state()
    snapshot = build_policy_snapshot(state)
    ctx = TurnContextView(raw_text="same")
    keys = [choose(snapshot, ctx).chosen.key.label() for _ in range(20)]
    assert len(set(keys)) == 1
