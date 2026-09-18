from __future__ import annotations

from packages.dialogue_engine.action_policy.actions import (
    ActionKind,
    CandidateAction,
    PolicyDecision,
    ScoredAction,
)
from packages.dialogue_engine.action_policy.bridge import (
    legacy_plan_to_action_key,
    to_response_plan,
)
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot
from packages.dialogue_engine.question_context import QuestionNeed
from packages.dialogue_engine.response_plan import ResponsePlan


def _decision(action: CandidateAction) -> PolicyDecision:
    scored = ScoredAction(action=action, score=1.0)
    return PolicyDecision(chosen=action, candidates=(scored,), rejected=(), policy_version="test")


def test_bridge_maps_episode_need_without_state_write() -> None:
    snapshot = PolicySnapshot.from_mapping(
        {
            "wellness_entry_covered": True,
            "episodes": [{"episode_id": "ep", "kind": "symptom", "known": {}}],
            "active_episode_id": "ep",
        }
    )
    before = snapshot
    action = CandidateAction(
        ActionKind.ASK_EPISODE,
        episode_id="ep",
        question_need=QuestionNeed.for_attribute("onset"),
    )
    plan = to_response_plan(_decision(action), snapshot)
    assert plan.episode_id == "ep"
    assert plan.question_needs[0].attribute == "onset"
    assert snapshot == before


def test_legacy_dynamic_episode_intents_normalize() -> None:
    onset = ResponsePlan(intent="episode_ep123_duration")
    current = ResponsePlan(intent="episode_ep123_current")
    assert legacy_plan_to_action_key(onset).label() == "ASK_EPISODE:temporal"
    assert legacy_plan_to_action_key(current).label() == "ASK_EPISODE:current"


def test_legacy_control_stop_normalizes_to_goodbye() -> None:
    plan = ResponsePlan(action="control", control="stop_call")
    assert legacy_plan_to_action_key(plan).label() == "GOODBYE_FINAL"
