"""Transparent linear scorer. Weights are human-written in Phase 1."""

from __future__ import annotations

from collections.abc import Mapping

from packages.dialogue_engine.action_policy.actions import CandidateAction, ScoredAction
from packages.dialogue_engine.action_policy.features import extract_features
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView

POLICY_VERSION = "action-policy-phase1-v3"

DEFAULT_WEIGHTS: dict[str, float] = {
    "bias": 0.0,
    "fit:safety": 100.0,
    "fit:goodbye": 95.0,
    "fit:control": 90.0,
    "fit:repair": 85.0,
    "fit:answer_user": 80.0,
    "fit:meta": 75.0,
    "fit:clarify": 70.0,
    "fit:episode": 12.0,
    "information_gain": 8.0,
    "unanswered_dimension_value": 10.0,
    "useful_follow_up": 22.0,
    "pending_need_match": 6.0,
    "active_issue": 2.0,
    "known_dimensions": -4.0,
    "enough_dimensions": -18.0,
    "episode_resolving": -20.0,
    "user_burden": -25.0,
    "episode_questions": -8.0,
    "repeat_penalty": -30.0,
    "fit:its": 30.0,
    "fit:background": 20.0,
    "fit:summary": 25.0,
    "fit:ack": 1.0,
    "new_grounded_issue": 0.2,
    "its_pending": 0.1,
    "transition_preferred": 45.0,
    "transition_penalty": -55.0,
}


def score_action(
    snapshot: PolicySnapshot,
    ctx: TurnContextView,
    action: CandidateAction,
    *,
    weights: Mapping[str, float] | None = None,
) -> ScoredAction:
    active = weights or DEFAULT_WEIGHTS
    features = extract_features(snapshot, ctx, action)
    contributions = {
        name: value * float(active.get(name, 0.0))
        for name, value in features.items()
        if value and active.get(name, 0.0)
    }
    return ScoredAction(
        action=action,
        score=sum(contributions.values()),
        features=features,
        contributions=contributions,
    )
