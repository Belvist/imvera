from __future__ import annotations

from packages.dialogue_engine.action_policy.actions import ActionKind, CandidateAction
from packages.dialogue_engine.action_policy.constraints import reject_candidate
from packages.dialogue_engine.action_policy.mandatory import MandatoryClass
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView
from packages.dialogue_engine.question_context import QuestionNeed


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


def test_known_need_is_hard_rejected() -> None:
    snap = _snap(
        episodes=[{"episode_id": "ep", "kind": "symptom", "known": {"onset": "yesterday"}}],
        active_episode_id="ep",
    )
    action = CandidateAction(
        ActionKind.ASK_EPISODE,
        episode_id="ep",
        question_need=QuestionNeed.for_attribute("duration"),
    )
    rejection = reject_candidate(snap, TurnContextView(), action)
    assert rejection is not None
    assert rejection.rule_id == "already_known"


def test_active_issue_blocks_background() -> None:
    snap = _snap(
        episodes=[{"episode_id": "ep", "kind": "symptom", "known": {}}],
        active_episode_id="ep",
        required_background_goals=["mood"],
    )
    action = CandidateAction(ActionKind.BACKGROUND_GOAL, target_goal="mood")
    rejection = reject_candidate(
        snap,
        TurnContextView(),
        action,
        mandatory_class=MandatoryClass.BACKGROUND_GOAL,
    )
    assert rejection is not None
    assert rejection.rule_id == "active_issue_blocks_background"


def test_explicit_farewell_is_not_a_scored_tradeoff() -> None:
    snap = _snap()
    ctx = TurnContextView(control="stop_call")
    ordinary = CandidateAction(ActionKind.IMPORTANT_TO_SHARE)
    rejection = reject_candidate(snap, ctx, ordinary)
    assert rejection is not None
    assert rejection.rule_id == "mandatory_class_mismatch"


def test_new_issue_blocks_close() -> None:
    snap = _snap(
        important_to_share_asked=True,
        important_to_share_resolved=True,
        episodes=[{"episode_id": "ep", "kind": "symptom", "known": {}}],
        active_episode_id="ep",
    )
    ctx = TurnContextView(has_new_issue=True)
    action = CandidateAction(ActionKind.SUMMARY_CLOSE)
    rejection = reject_candidate(
        snap,
        ctx,
        action,
        mandatory_class=MandatoryClass.SUMMARY_CLOSE,
    )
    assert rejection is not None
    assert rejection.rule_id in {"premature_close_new_issue", "premature_close_issue"}


def test_other_person_episode_cannot_be_asked() -> None:
    snap = _snap(
        episodes=[
            {
                "episode_id": "ep-other",
                "kind": "symptom",
                "known": {},
                "speaker_owned": False,
            }
        ],
        active_episode_id="ep-other",
    )
    action = CandidateAction(
        ActionKind.ASK_EPISODE,
        episode_id="ep-other",
        question_need=QuestionNeed.for_attribute("onset"),
    )
    rejection = reject_candidate(
        snap,
        TurnContextView(has_new_issue=True),
        action,
        mandatory_class=MandatoryClass.CONVERSATION,
    )
    assert rejection is not None
    assert rejection.rule_id in {"wrong_subject", "episode_not_interrogatable"}
