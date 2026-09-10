"""v7 optional-need lifecycle regressions (A–H) + candidate/utility invariant."""

from __future__ import annotations

from packages.dialogue_engine.action_policy.actions import (
    ActionKind,
    PolicyConstraintViolation,
    normalize_need,
)
from packages.dialogue_engine.action_policy.need_value import (
    best_remaining_ask_utility,
    currently_askable_needs,
    interrogation_intentionally_left,
    need_ask_utility,
    need_is_currently_askable,
    outstanding_pending_obligation,
)
from packages.dialogue_engine.action_policy.policy import choose, generate_candidates
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


def test_a_optional_fi_after_its_does_not_block_close() -> None:
    snap = _snap(
        important_to_share_asked=True,
        important_to_share_resolved=True,
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
    )
    ctx = TurnContextView(raw_text="больше ничего")
    decision = choose(snap, ctx)
    assert decision.chosen.kind == ActionKind.SUMMARY_CLOSE
    assert decision.chosen.kind != ActionKind.ACK_ONLY
    labels = {item.action.key.label() for item in decision.candidates}
    assert "ASK_EPISODE:functional_impact" not in labels


def test_b_optional_leftover_after_its_does_not_restart_interrogation() -> None:
    snap = _snap(
        important_to_share_asked=True,
        important_to_share_resolved=True,
        user_burden=1.0,
        questions_asked_this_episode=3,
        episodes=[
            {
                "episode_id": "ep-1",
                "kind": "symptom",
                "known": {"onset": "вчера"},
            }
        ],
        active_episode_id="ep-1",
        last_question_need="temporal",
    )
    decision = choose(snap, TurnContextView(raw_text="больше ничего"))
    assert decision.chosen.kind == ActionKind.SUMMARY_CLOSE
    assert all(item.action.kind != ActionKind.ASK_EPISODE for item in decision.candidates)


def test_c_low_burden_optional_fi_may_be_asked_before_transition() -> None:
    snap = _snap(
        user_burden=0.05,
        questions_asked_this_episode=0,
        episodes=[
            {
                "episode_id": "ep-1",
                "kind": "function_issue",
                "known": {"onset": "месяц", "current": "active"},
            }
        ],
        active_episode_id="ep-1",
    )
    assert not interrogation_intentionally_left(snap)
    ep = snap.active_episode
    assert ep is not None
    assert need_is_currently_askable(snap, ep, "functional_impact")
    labels = {c.key.label() for c in generate_candidates(snap, TurnContextView())}
    assert "ASK_EPISODE:functional_impact" in labels
    # Utility path may still prefer ITS when core needs are done; candidate must exist.
    util = need_ask_utility(snap, ep, "functional_impact")
    assert util > 0.0


def test_d_high_burden_transition_may_win_over_optional() -> None:
    snap = _snap(
        user_burden=1.0,
        questions_asked_this_episode=3,
        episodes=[
            {
                "episode_id": "ep-1",
                "kind": "function_issue",
                "known": {"onset": "месяц", "current": "active"},
            }
        ],
        active_episode_id="ep-1",
    )
    decision = choose(snap, TurnContextView(raw_text="угу"))
    assert decision.chosen.kind == ActionKind.IMPORTANT_TO_SHARE


def test_e_pending_fi_is_hard_obligation() -> None:
    snap = _snap(
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
    assert outstanding_pending_obligation(snap)
    decision = choose(snap, TurnContextView())
    assert decision.chosen.key.label() == "ASK_EPISODE:functional_impact"
    forbidden = {
        r.action.key.label()
        for r in decision.rejected
        if r.rule_id
        in {
            "pending_obligation_blocks_its",
            "pending_obligation_blocks_close",
            "mandatory_class_mismatch",
        }
    }
    assert "IMPORTANT_TO_SHARE" in {
        r.action.key.label() for r in decision.rejected
    } or decision.chosen.kind != ActionKind.IMPORTANT_TO_SHARE
    # Directly ensure ITS/SUMMARY are not chosen.
    assert decision.chosen.kind not in {
        ActionKind.IMPORTANT_TO_SHARE,
        ActionKind.SUMMARY_CLOSE,
    }
    del forbidden


def test_f_preemption_keeps_pending_resumable() -> None:
    snap = _snap(
        episodes=[
            {
                "episode_id": "ep-1",
                "kind": "symptom",
                "known": {"onset": "вчера"},
            }
        ],
        active_episode_id="ep-1",
        pending_episode_attribute="current",
    )
    assert outstanding_pending_obligation(snap)
    preempt = choose(
        snap,
        TurnContextView(raw_text="повторите", dialogue_act="repair"),
    )
    assert preempt.chosen.kind == ActionKind.REPAIR
    # After preemption handled, same obligation remains askable.
    resume = choose(snap, TurnContextView(raw_text=""))
    assert resume.chosen.key.label() == "ASK_EPISODE:current"


def test_g_completed_active_does_not_hide_pending_episode() -> None:
    snap = _snap(
        important_to_share_asked=True,
        important_to_share_resolved=False,
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
    decision = choose(
        snap,
        TurnContextView(raw_text="ещё плечо", has_new_speaker_issue=True),
    )
    assert decision.chosen.kind == ActionKind.ASK_EPISODE
    assert decision.chosen.episode_id == "ep-b"


def test_h_askable_utility_needs_have_candidates() -> None:
    """Invariant: every currently-askable need has a generated ASK candidate."""
    matrices = [
        _snap(
            episodes=[{"episode_id": "ep-1", "kind": "symptom", "known": {}}],
            active_episode_id="ep-1",
        ),
        _snap(
            episodes=[
                {
                    "episode_id": "ep-1",
                    "kind": "symptom",
                    "known": {"onset": "вчера"},
                }
            ],
            active_episode_id="ep-1",
        ),
        _snap(
            episodes=[
                {
                    "episode_id": "ep-1",
                    "kind": "function_issue",
                    "known": {"onset": "месяц", "current": "active"},
                }
            ],
            active_episode_id="ep-1",
        ),
        _snap(
            episodes=[
                {
                    "episode_id": "ep-1",
                    "kind": "function_issue",
                    "known": {"onset": "месяц", "current": "active"},
                }
            ],
            active_episode_id="ep-1",
            pending_episode_attribute="functional_impact",
        ),
        _snap(
            important_to_share_resolved=True,
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
        ),
        _snap(
            important_to_share_asked=True,
            episodes=[
                {
                    "episode_id": "ep-a",
                    "kind": "symptom",
                    "known": {"onset": "давно", "current": "active"},
                },
                {"episode_id": "ep-b", "kind": "symptom", "known": {}},
            ],
            active_episode_id="ep-a",
            pending_episode_ids=["ep-b"],
        ),
    ]
    for snap in matrices:
        askable = currently_askable_needs(snap, ctx=TurnContextView())
        generated = {
            (c.episode_id, normalize_need(c.question_need))
            for c in generate_candidates(snap, TurnContextView())
            if c.kind == ActionKind.ASK_EPISODE
        }
        for episode_id, need in askable:
            assert (episode_id, need) in generated, (
                f"askable {(episode_id, need)} missing from candidates {generated}; "
                f"utility={best_remaining_ask_utility(snap)}"
            )


def test_optional_after_its_not_in_best_remaining_utility() -> None:
    snap = _snap(
        important_to_share_resolved=True,
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
    )
    assert currently_askable_needs(snap) == ()
    assert best_remaining_ask_utility(snap) == 0.0
    assert not snap.has_askable_open_issues()


def test_no_constraint_violation_on_its_resolved_optional_fi() -> None:
    snap = _snap(
        important_to_share_asked=True,
        important_to_share_resolved=True,
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
    )
    try:
        choose(snap, TurnContextView(raw_text="нет"))
    except PolicyConstraintViolation as exc:  # pragma: no cover - must not fire
        raise AssertionError(f"unexpected constraint violation: {exc}") from exc
