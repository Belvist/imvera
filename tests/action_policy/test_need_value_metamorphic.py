from __future__ import annotations

from packages.dialogue_engine.action_policy.actions import ActionKind
from packages.dialogue_engine.action_policy.need_value import (
    best_remaining_ask_utility,
    need_ask_utility,
    outstanding_pending_obligation,
    transition_preferred,
)
from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView


def _snap(**updates) -> PolicySnapshot:
    raw = {
        "turn_number": 4,
        "wellness_entry_covered": True,
        "background_goal_status": {
            "wellness": "answered",
            "mood": "unseen",
            "sleep": "unseen",
            "plans": "unseen",
        },
    }
    raw.update(updates)
    return PolicySnapshot.from_mapping(raw)


def test_extra_known_dimension_does_not_erase_pending_obligation() -> None:
    base = _snap(
        episodes=[
            {
                "episode_id": "ep-1",
                "kind": "symptom",
                "known": {"onset": "вчера", "current": "active"},
            }
        ],
        active_episode_id="ep-1",
        pending_episode_attribute="functional_impact",
    )
    richer = _snap(
        episodes=[
            {
                "episode_id": "ep-1",
                "kind": "symptom",
                "known": {
                    "onset": "вчера",
                    "current": "active",
                    "severity": "лёгкая",
                },
            }
        ],
        active_episode_id="ep-1",
        pending_episode_attribute="functional_impact",
    )
    assert outstanding_pending_obligation(base)
    assert outstanding_pending_obligation(richer)
    decision = choose(base, TurnContextView())
    assert decision.chosen.kind != ActionKind.IMPORTANT_TO_SHARE


def test_pending_obligation_blocks_transition_more_than_optional_ask() -> None:
    before = _snap(
        episodes=[
            {
                "episode_id": "ep-1",
                "kind": "function_issue",
                "known": {"onset": "месяц", "current": "active"},
            }
        ],
        active_episode_id="ep-1",
    )
    after = _snap(
        episodes=[
            {
                "episode_id": "ep-1",
                "kind": "function_issue",
                "known": {"onset": "месяц", "current": "active"},
            }
        ],
        active_episode_id="ep-1",
        pending_episode_attribute="functional_impact",
    )
    assert outstanding_pending_obligation(after)
    assert not transition_preferred(after)
    if transition_preferred(before):
        assert not transition_preferred(after)


def test_high_burden_may_suppress_optional_but_not_pending_obligation() -> None:
    optional = _snap(
        user_burden=0.95,
        questions_asked_this_episode=3,
        episodes=[
            {
                "episode_id": "ep-1",
                "kind": "symptom",
                "known": {"onset": "вчера", "severity": "лёгкая"},
            }
        ],
        active_episode_id="ep-1",
        last_question_need="severity",
    )
    pending = _snap(
        user_burden=0.95,
        questions_asked_this_episode=3,
        episodes=[
            {
                "episode_id": "ep-1",
                "kind": "function_issue",
                "known": {"onset": "месяц", "current": "active"},
            }
        ],
        active_episode_id="ep-1",
        pending_episode_attribute="functional_impact",
    )
    ep = optional.active_episode
    assert ep is not None
    low_burden = _snap(
        user_burden=0.1,
        episodes=[
            {
                "episode_id": "ep-1",
                "kind": "symptom",
                "known": {"onset": "вчера", "severity": "лёгкая"},
            }
        ],
        active_episode_id="ep-1",
        last_question_need="severity",
    )
    low_ep = low_burden.active_episode
    assert low_ep is not None
    assert need_ask_utility(optional, ep, "current") < need_ask_utility(
        low_burden,
        low_ep,
        "current",
    )
    assert outstanding_pending_obligation(pending)
    assert choose(pending, TurnContextView()).chosen.kind == ActionKind.ASK_EPISODE


def test_pending_functional_impact_still_generates_ask_candidate() -> None:
    snap = _snap(
        episodes=[
            {
                "episode_id": "ep-1",
                "kind": "symptom",
                "known": {
                    "onset": "месяц",
                    "current": "active",
                    "severity": "лёгкая",
                },
            }
        ],
        active_episode_id="ep-1",
        pending_episode_attribute="functional_impact",
    )
    ep = snap.active_episode
    assert ep is not None
    assert ep.has_open_questions
    decision = choose(snap, TurnContextView())
    assert decision.chosen.kind == ActionKind.ASK_EPISODE
    assert decision.chosen.question_need is not None


def test_completed_active_does_not_hide_pending_episode_need() -> None:
    snap = _snap(
        episodes=[
            {
                "episode_id": "ep-a",
                "kind": "symptom",
                "known": {
                    "onset": "давно",
                    "current": "resolved",
                    "severity": "лёгкая",
                },
            },
            {"episode_id": "ep-b", "kind": "symptom", "known": {}},
        ],
        active_episode_id="ep-a",
        pending_episode_ids=["ep-b"],
    )
    decision = choose(snap, TurnContextView())
    assert decision.chosen.kind == ActionKind.ASK_EPISODE
    assert decision.chosen.episode_id == "ep-b"
