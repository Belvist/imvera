"""ActionPolicy v8 hard invariants (property-style)."""

from __future__ import annotations

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.action_policy.actions import ActionKind, CandidateAction
from packages.dialogue_engine.action_policy.constraints import reject_candidate
from packages.dialogue_engine.action_policy.mandatory import compute_mandatory_class
from packages.dialogue_engine.action_policy.policy import choose, generate_candidates
from packages.dialogue_engine.action_policy.snapshot import (
    TurnContextView,
    build_policy_snapshot,
)
from packages.dialogue_engine.question_context import QuestionNeed
from packages.dialogue_engine.state import EngineState, IssueEpisode


def _state_with_pending(need: str = "current") -> EngineState:
    state = EngineState(call_id="inv", turn_seq=2, first_user_turn_received=True)
    state.slots["wellness"] = SlotStatus.FILLED
    state.background_goal_status["wellness"] = "answered"
    state.issue_episodes["ep-1"] = IssueEpisode(
        episode_id="ep-1",
        primary_label="колено",
        kind="symptom",
        known_attributes={"onset": "вчера"},
        status="open",
    )
    state.active_episode_id = "ep-1"
    state.pending_episode_attribute = need
    return state


def test_invariant_pending_never_silently_lost() -> None:
    snap = build_policy_snapshot(_state_with_pending("current"))
    decision = choose(snap, TurnContextView())
    assert decision.chosen.key.label() == "ASK_EPISODE:current"


def test_invariant_safety_beats_everything() -> None:
    snap = build_policy_snapshot(_state_with_pending("current"))
    ctx = TurnContextView(raw_text="помогите", turn_risk_level="urgent")
    assert choose(snap, ctx).chosen.kind == ActionKind.SAFETY


def test_invariant_control_beats_scheduling() -> None:
    snap = build_policy_snapshot(_state_with_pending("current"))
    ctx = TurnContextView(control="defer")
    decision = choose(snap, ctx)
    assert decision.chosen.kind == ActionKind.CONTROL


def test_invariant_its_does_not_close_hard_pending() -> None:
    snap = build_policy_snapshot(_state_with_pending("current"))
    its = CandidateAction(kind=ActionKind.IMPORTANT_TO_SHARE)
    ctx = TurnContextView()
    rejection = reject_candidate(snap, ctx, its)
    assert rejection is not None
    assert rejection.rule_id == "pending_obligation_blocks_its"


def test_invariant_summary_impossible_with_hard_pending() -> None:
    snap = build_policy_snapshot(_state_with_pending("current"))
    close = CandidateAction(kind=ActionKind.SUMMARY_CLOSE)
    rejection = reject_candidate(snap, TurnContextView(), close)
    assert rejection is not None
    assert rejection.rule_id in {
        "pending_obligation_blocks_close",
        "mandatory_class_mismatch",
    }


def test_invariant_askable_hard_need_has_candidate() -> None:
    snap = build_policy_snapshot(_state_with_pending("current"))
    ctx = TurnContextView()
    labels = {a.key.label() for a in generate_candidates(snap, ctx)}
    assert "ASK_EPISODE:current" in labels
    mandatory = compute_mandatory_class(snap, ctx)
    ask = CandidateAction(
        kind=ActionKind.ASK_EPISODE,
        episode_id="ep-1",
        question_need=QuestionNeed(
            attributes=("current",),
            accepted_semantics=("current", "status"),
        ),
    )
    # Must not be hard-rejected while it is the pending obligation.
    assert reject_candidate(snap, ctx, ask, mandatory_class=mandatory) is None
