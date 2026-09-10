"""Transparent linear scorer. Weights are human-written in Phase 1."""

from __future__ import annotations

from collections.abc import Mapping

from packages.dialogue_engine.action_policy.actions import CandidateAction, ScoredAction
from packages.dialogue_engine.action_policy.features import extract_features
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView

POLICY_VERSION = "action-policy-phase1-v6"

DEFAULT_WEIGHTS: dict[str, float] = {
    "bias": 0.0,
    "fit:safety": 100.0,
    "fit:goodbye": 95.0,
    "fit:control": 90.0,
    "fit:repair": 85.0,
    "fit:answer_user": 80.0,
    "fit:meta": 75.0,
    "fit:clarify": 70.0,
    "fit:episode": 14.0,
    "information_value": 10.0,
    "need_ask_utility": 28.0,
    "pending_obligation": 35.0,
    "episode_resolving": -20.0,
    "ask_burden_penalty": -22.0,
    "transition_burden_relief": 42.0,
    "episode_question_cost": -7.0,
    "repeat_penalty": -32.0,
    "fit:its": 28.0,
    "fit:background": 20.0,
    "fit:summary": 25.0,
    "fit:ack": 1.0,
    "new_grounded_issue": 0.2,
    "its_pending": 0.1,
    "transition_preferred": 40.0,
    "transition_penalty": -50.0,
    "transition_utility": 18.0,
    "best_remaining_need_penalty": -32.0,
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
