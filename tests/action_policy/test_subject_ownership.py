from __future__ import annotations

from packages.dialogue_engine.action_policy.actions import ActionKind
from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.semantic_signals import classify_turn_issues
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView
from packages.dialogue_engine.semantic_kernel.types import Observation, SubjectKind
from packages.dialogue_engine.state import BackgroundGoalCoverage, EngineState, SlotStatus
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text


def _other_person_snapshot() -> PolicySnapshot:
    return PolicySnapshot.from_mapping(
        {
            "turn_number": 2,
            "wellness_entry_covered": True,
            "episodes": [
                {
                    "episode_id": "ep-other",
                    "kind": "symptom",
                    "known": {},
                    "speaker_owned": False,
                }
            ],
            "active_episode_id": "ep-other",
            "background_goal_status": {
                "wellness": "answered",
                "mood": "unseen",
                "sleep": "unseen",
                "plans": "unseen",
            },
        }
    )


def test_classify_turn_issues_uses_observation_subject() -> None:
    speaker, other = classify_turn_issues(
        issue_mentions=(object(),),
        observations=(
            Observation(
                observation_id="o1",
                attribute="issue",
                value="heart pain",
                subject=SubjectKind.OTHER_PERSON,
            ),
        ),
    )
    assert not speaker
    assert other


def test_third_person_plus_speaker_wellness_allows_its() -> None:
    state = EngineState(call_id="flow-e")
    state.turn_seq = 2
    state.slots["wellness"] = SlotStatus.FILLED
    state.background_goal_status["wellness"] = BackgroundGoalCoverage.ANSWERED.value

    rich = build_rich_turn_from_text(
        "У мужа что-то болит, а я нормально.",
        utterance_id="u-flow-e",
        engine_state=state,
    )
    ctx = TurnContextView.from_turn(rich)
    decision = choose(_other_person_snapshot(), ctx)
    assert decision.chosen.kind == ActionKind.IMPORTANT_TO_SHARE
    assert decision.chosen.kind != ActionKind.ACK_ONLY


def test_other_person_only_context_prefers_its_not_ack() -> None:
    snapshot = _other_person_snapshot()
    ctx = TurnContextView.from_mapping(
        {
            "raw_text": "У мужа что-то болит, а я нормально.",
            "has_new_other_person_issue": True,
            "has_new_speaker_issue": False,
        }
    )
    decision = choose(snapshot, ctx)
    assert decision.chosen.kind == ActionKind.IMPORTANT_TO_SHARE
