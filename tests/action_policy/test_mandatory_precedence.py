from __future__ import annotations

import pytest

from packages.dialogue_engine.action_policy.actions import (
    ActionKind,
    CandidateAction,
    PolicyConstraintViolation,
)
from packages.dialogue_engine.action_policy.mandatory import MandatoryClass, compute_mandatory_class
from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView


def _snap(**updates) -> PolicySnapshot:
    raw = {
        "turn_number": 2,
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


def test_urgent_plus_repair_chooses_safety_not_ack() -> None:
    snap = _snap(risk_level="urgent")
    ctx = TurnContextView(dialogue_act="repair")
    decision = choose(snap, ctx)
    assert decision.chosen.kind == ActionKind.SAFETY
    assert compute_mandatory_class(snap, ctx) == MandatoryClass.SAFETY


def test_farewell_plus_repair_chooses_goodbye_not_ack() -> None:
    snap = _snap()
    ctx = TurnContextView(control="stop_call", dialogue_act="repair")
    decision = choose(snap, ctx)
    assert decision.chosen.kind == ActionKind.GOODBYE_FINAL
    assert compute_mandatory_class(snap, ctx) == MandatoryClass.TERMINAL_CONTROL


def test_control_defer_plus_user_question_chooses_control() -> None:
    snap = _snap()
    ctx = TurnContextView(control="defer", user_question=True)
    decision = choose(snap, ctx)
    assert decision.chosen.kind == ActionKind.CONTROL
    assert decision.chosen.control == "defer"
    assert compute_mandatory_class(snap, ctx) == MandatoryClass.TERMINAL_CONTROL


def test_zero_survivors_raises_not_ack_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    snap = _snap()
    ctx = TurnContextView(dialogue_act="repair")
    monkeypatch.setattr(
        "packages.dialogue_engine.action_policy.policy.generate_candidates",
        lambda _snapshot, _ctx: (CandidateAction(ActionKind.ACK_ONLY),),
    )
    with pytest.raises(PolicyConstraintViolation) as exc:
        choose(snap, ctx)
    assert exc.value.mandatory_class == MandatoryClass.REPAIR.value


def test_ack_only_mandatory_when_no_higher_class() -> None:
    snap = _snap(important_to_share_asked=True, important_to_share_resolved=False)
    ctx = TurnContextView(raw_text="угу", dialogue_act="answer")
    decision = choose(snap, ctx)
    assert decision.chosen.kind == ActionKind.ACK_ONLY
    assert compute_mandatory_class(snap, ctx) == MandatoryClass.CONVERSATION


def test_improving_new_issue_transitions_to_its_not_ack() -> None:
    snap = _snap(
        episodes=[
            {
                "episode_id": "ep-h",
                "kind": "symptom",
                "known": {"onset": "с утра", "current": "improving"},
            }
        ],
        active_episode_id="ep-h",
    )
    ctx = TurnContextView(
        raw_text="Голова болела, но уже почти прошла.",
        has_new_issue=True,
    )
    decision = choose(snap, ctx)
    assert decision.chosen.kind == ActionKind.IMPORTANT_TO_SHARE
    assert decision.chosen.kind != ActionKind.ACK_ONLY
