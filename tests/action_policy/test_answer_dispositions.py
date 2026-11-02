"""Unknown/refusal discharges a question, without becoming medical knowledge."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.action_policy.actions import ActionKind, CandidateAction
from packages.dialogue_engine.action_policy.constraints import reject_candidate
from packages.dialogue_engine.action_policy.need_value import currently_askable_needs
from packages.dialogue_engine.action_policy.policy import generate_candidates
from packages.dialogue_engine.action_policy.snapshot import (
    PolicySnapshot,
    TurnContextView,
    build_policy_snapshot,
)
from packages.dialogue_engine.question_context import QuestionNeed
from packages.dialogue_engine.state import EngineState, IssueEpisode


@pytest.mark.parametrize(
    "disposed,requested",
    [
        ("onset", "duration"),
        ("duration", "onset"),
        ("current", "status"),
        ("severity", "severity"),
        ("associated", "associated"),
    ],
)
def test_answer_disposition_is_preserved_and_hard_excludes_reasking(disposed, requested):
    state = EngineState(call_id="unknown-policy")
    state.issue_episodes["e1"] = IssueEpisode(
        episode_id="e1",
        primary_label="головная боль",
        kind="symptom",
        subject="speaker",
        unanswered_attributes={disposed: "Не помню."},
    )
    state.active_episode_id = "e1"
    # Even an old pending projection may not recreate a discharged question.
    state.pending_episode_attribute = requested
    before = state.model_dump(mode="json")
    snapshot = build_policy_snapshot(state)
    ep = snapshot.episode("e1")
    assert not ep.need_known(requested)
    action = CandidateAction(
        ActionKind.ASK_EPISODE, episode_id="e1", question_need=QuestionNeed.for_attribute(requested)
    )
    rejection = reject_candidate(snapshot, TurnContextView(), action)
    assert rejection is not None
    assert rejection.rule_id == "answer_disposition"
    assert not snapshot.outstanding_pending_obligation()
    assert action not in generate_candidates(snapshot, TurnContextView())
    assert state.model_dump(mode="json") == before


def test_mapping_and_live_snapshot_keep_unknown_separate_from_known():
    snapshot = PolicySnapshot.from_mapping(
        {
            "episodes": [{"episode_id": "e1", "unanswered_attributes": {"onset": "Не помню."}}],
            "active_episode_id": "e1",
            "wellness_entry_covered": True,
        }
    )
    ep = snapshot.episode("e1")
    assert not ep.temporal_known
    assert not any(need == "temporal" for _, need in currently_askable_needs(snapshot))
    assert any(need == "current" for _, need in currently_askable_needs(snapshot))


def test_historical_temporal_exhaustion_cannot_recreate_temporal_question():
    snapshot = PolicySnapshot.from_mapping(
        {
            "episodes": [{"episode_id": "e1", "known": {"_temporal_skipped": "1"}}],
            "active_episode_id": "e1",
            "wellness_entry_covered": True,
        }
    )
    assert not snapshot.episode("e1").temporal_known
    assert not any(need == "temporal" for _, need in currently_askable_needs(snapshot))


@pytest.mark.parametrize("reply", ["Не помню.", "Не хочу отвечать."])
def test_real_sdk_unavailable_moves_to_another_need_without_inventing_onset(monkeypatch, reply):
    from packages.dialogue_engine.engine import DialogueEngine

    for key, value in {
        "IMVERA_DIALOGUE_ENGINE": "1",
        "IMVERA_COVERAGE_LADDER": "0",
        "IMVERA_ACTION_POLICY_MODE": "policy",
        "IMVERA_ACTION_POLICY_CUTOVER_ENABLED": "1",
        "IMVERA_LLM_INTERPRET": "0",
        "IMVERA_MISSION_LLM_INTERPRET": "0",
    }.items():
        monkeypatch.setenv(key, value)
    engine = DialogueEngine(call_id="sdk-unknown-policy")

    def deliver():
        while (speech := engine.pop_speak_effect()) is not None:
            engine.on_playout_completed(speech.generation, speech.question_id)

    engine.start()
    deliver()
    for uid, text in (("u1", "Голова болит."), ("u2", reply)):
        engine.on_user_turn(uid, text, rich_turn=engine.build_rich_turn(text, utterance_id=uid))
        deliver()
    ep = next(iter(engine.state.issue_episodes.values()))
    assert not ep.known_attributes.get("onset") and not ep.known_attributes.get("duration")
    assert ep.unanswered_attributes
    assert reply in ep.unanswered_attributes.values()
    suffix = "declined" if reply == "Не хочу отвечать." else "unknown"
    assert any(k.endswith("_" + suffix) and v == reply
               for k, v in engine.state.observations.items())
    assert engine.state.pending_episode_attribute not in {"onset", "duration", "temporal"}
    assert not engine.state.call_closed
