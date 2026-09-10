from __future__ import annotations

from packages.dialogue_engine.action_policy.actions import ActionKind
from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView


def _base_snapshot(**updates) -> PolicySnapshot:
    raw = {
        "turn_number": 5,
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


def test_pending_episode_blocks_transition_while_active_is_rich() -> None:
    snapshot = _base_snapshot(
        episodes=[
            {
                "episode_id": "ep-A",
                "kind": "symptom",
                "known": {"onset": "yesterday", "current": "active"},
            },
            {"episode_id": "ep-B", "kind": "symptom", "known": {}},
        ],
        active_episode_id="ep-A",
        pending_episode_ids=["ep-B"],
    )
    ctx = TurnContextView()
    assert not snapshot.transition_preferred(ctx)
    decision = choose(snapshot, ctx)
    assert decision.chosen.kind == ActionKind.ASK_EPISODE
    assert decision.chosen.episode_id == "ep-B"
    assert decision.chosen.kind != ActionKind.IMPORTANT_TO_SHARE


def test_complete_active_plus_new_pending_prefers_pending_episode() -> None:
    snapshot = _base_snapshot(
        episodes=[
            {
                "episode_id": "ep-A",
                "kind": "symptom",
                "known": {"onset": "yesterday", "current": "resolved"},
                "status": "open",
            },
            {"episode_id": "ep-B", "kind": "symptom", "known": {}},
        ],
        active_episode_id="ep-A",
        pending_episode_ids=["ep-B"],
    )
    decision = choose(snapshot, ctx=TurnContextView(has_new_speaker_issue=True))
    assert decision.chosen.kind == ActionKind.ASK_EPISODE
    assert decision.chosen.episode_id == "ep-B"
