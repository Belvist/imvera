"""ActionPolicy v8 live-builder parity — EngineState → build_policy_snapshot → choose."""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.action_policy.actions import ActionKind
from packages.dialogue_engine.action_policy.constraints import reject_candidate
from packages.dialogue_engine.action_policy.policy import choose, generate_candidates
from packages.dialogue_engine.action_policy.scorer import POLICY_VERSION
from packages.dialogue_engine.action_policy.snapshot import (
    TurnContextView,
    build_policy_snapshot,
)
from packages.dialogue_engine.state import EngineState, IssueEpisode, Question


def _base_state(**kwargs) -> EngineState:
    state = EngineState(
        call_id="v8-live",
        turn_seq=4,
        processing_turn_id="u-4",
        first_user_turn_received=True,
    )
    state.slots["wellness"] = SlotStatus.FILLED
    state.background_goal_status["wellness"] = "answered"
    for key, value in kwargs.items():
        setattr(state, key, value)
    return state


def _episode(**known) -> IssueEpisode:
    return IssueEpisode(
        episode_id="ep-1",
        primary_label="колено",
        kind="symptom",
        known_attributes=dict(known),
        status="open",
    )


def test_policy_version_is_v9() -> None:
    assert POLICY_VERSION == "action-policy-phase1-v9"


def test_live_pending_current_not_mirrored_into_delivered_need() -> None:
    state = _base_state()
    state.issue_episodes["ep-1"] = _episode(onset="вчера")
    state.active_episode_id = "ep-1"
    state.pending_episode_attribute = "current"
    # No delivered question on state.
    snap = build_policy_snapshot(state)
    assert snap.pending_episode_attribute == "current"
    assert snap.outstanding_pending_obligation() is True
    assert snap.last_delivered_question_need is None
    assert snap.last_question_need is None


def test_live_pending_current_survives_repeat_constraint() -> None:
    state = _base_state()
    state.issue_episodes["ep-1"] = _episode(onset="вчера")
    state.active_episode_id = "ep-1"
    state.pending_episode_attribute = "current"
    # Delivered the same need (playing/delivered) but still unanswered pending.
    state.delivered_question = Question(
        question_id="q1",
        intent="episode_current_status",
        slot="episode_current_status",
        text="ещё беспокоит?",
    )
    snap = build_policy_snapshot(state)
    assert snap.last_delivered_question_need == "current"
    assert snap.pending_episode_attribute == "current"
    ctx = TurnContextView()
    decision = choose(snap, ctx)
    assert decision.chosen.kind == ActionKind.ASK_EPISODE
    assert decision.chosen.key.label() == "ASK_EPISODE:current"
    assert "repeat_question" not in {r.rule_id for r in decision.rejected}


@pytest.mark.parametrize(
    "pending,known,label",
    [
        ("temporal", {}, "ASK_EPISODE:temporal"),
        ("current", {"onset": "вчера"}, "ASK_EPISODE:current"),
        ("severity", {"onset": "вчера", "current": "active"}, "ASK_EPISODE:severity"),
        (
            "functional_impact",
            {"onset": "вчера", "current": "active", "severity": "лёгкая"},
            "ASK_EPISODE:functional_impact",
        ),
    ],
)
def test_live_pending_needs_are_choosable(pending: str, known: dict, label: str) -> None:
    state = _base_state()
    state.issue_episodes["ep-1"] = _episode(**known)
    state.active_episode_id = "ep-1"
    state.pending_episode_attribute = pending
    snap = build_policy_snapshot(state)
    decision = choose(snap, TurnContextView())
    assert decision.chosen.key.label() == label


def test_repeat_still_blocks_when_not_pending_obligation() -> None:
    state = _base_state()
    state.issue_episodes["ep-1"] = _episode(onset="вчера")
    state.active_episode_id = "ep-1"
    state.pending_episode_attribute = None
    state.delivered_question = Question(
        question_id="q1",
        intent="episode_current_status",
        slot="episode_current_status",
        text="ещё беспокоит?",
    )
    snap = build_policy_snapshot(state)
    assert snap.last_delivered_question_need == "current"
    ctx = TurnContextView()
    for action in generate_candidates(snap, ctx):
        if action.key.label() == "ASK_EPISODE:current":
            rejection = reject_candidate(snap, ctx, action)
            assert rejection is not None
            assert rejection.rule_id == "repeat_question"
            break
    else:
        pytest.fail("expected ASK_EPISODE:current candidate")


def test_its_cannot_close_over_hard_pending() -> None:
    state = _base_state()
    state.issue_episodes["ep-1"] = _episode(onset="вчера")
    state.active_episode_id = "ep-1"
    state.pending_episode_attribute = "current"
    snap = build_policy_snapshot(state)
    decision = choose(snap, TurnContextView())
    assert decision.chosen.kind != ActionKind.IMPORTANT_TO_SHARE
    assert decision.chosen.kind != ActionKind.SUMMARY_CLOSE


def test_safety_preempts_pending() -> None:
    state = _base_state()
    state.issue_episodes["ep-1"] = _episode(onset="вчера")
    state.active_episode_id = "ep-1"
    state.pending_episode_attribute = "current"
    snap = build_policy_snapshot(state)
    ctx = TurnContextView(raw_text="не могу дышать", turn_risk_level="urgent")
    decision = choose(snap, ctx)
    assert decision.chosen.kind == ActionKind.SAFETY


def test_multi_episode_pending_preserved() -> None:
    state = _base_state()
    state.issue_episodes["ep-a"] = IssueEpisode(
        episode_id="ep-a",
        primary_label="голова",
        kind="symptom",
        known_attributes={"onset": "вчера", "current": "active"},
        status="open",
    )
    state.issue_episodes["ep-b"] = IssueEpisode(
        episode_id="ep-b",
        primary_label="плечо",
        kind="symptom",
        known_attributes={},
        status="open",
    )
    state.active_episode_id = "ep-a"
    state.pending_episode_ids = ["ep-b"]
    state.pending_episode_attribute = "severity"
    snap = build_policy_snapshot(state)
    decision = choose(snap, TurnContextView())
    assert decision.chosen.key.label() == "ASK_EPISODE:severity"
    assert decision.chosen.episode_id == "ep-a"
