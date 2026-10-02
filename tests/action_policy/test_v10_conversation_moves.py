"""User-led moves reuse choose; medical/consent ownership remains hard."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.action_policy.actions import ActionKey, ActionKind, CandidateAction
from packages.dialogue_engine.action_policy.constraints import reject_candidate
from packages.dialogue_engine.action_policy.mandatory import thread_context_eligible
from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.snapshot import (
    PolicySnapshot,
    TurnContextView,
    build_policy_snapshot,
)
from packages.dialogue_engine.state import EngineState

CASES = json.loads((Path(__file__).parent / "corpus/conversation_v10/scenarios.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_thread_moves_and_protected_contexts(case):
    snap = PolicySnapshot.from_mapping(case["snapshot"])
    ctx = TurnContextView.from_mapping(case["context"])
    before = copy.deepcopy((snap, ctx))
    decision = choose(snap, ctx)
    assert (snap, ctx) == before
    if case["expected_v10_action"]:
        assert decision.chosen.key.label() == case["expected_v10_action"]
    else:
        assert decision.chosen.thread_mode is None
        assert decision.chosen.kind != ActionKind.FOLLOW_USER_THREAD


def test_thread_count_never_forces_resume():
    snap = PolicySnapshot.from_mapping(CASES[1]["snapshot"])
    ctx = TurnContextView(utterance_id="u1")
    assert {
        choose(replace(snap, thread_question_count=n), ctx).chosen.key.label()
        for n in (0, 1, 2, 10, 1000)
    } == {"ACK_ONLY:listen"}


def test_thread_modes_distinguish_action_keys():
    ordinary = ActionKey(ActionKind.ACK_ONLY)
    listener = CandidateAction(ActionKind.ACK_ONLY, thread_mode="listen")
    assert ordinary != listener.key
    assert listener.key.label() == "ACK_ONLY:listen"
    assert reject_candidate(PolicySnapshot(), TurnContextView(), listener) is not None


def test_required_background_is_deferred_and_remains_uncovered():
    snap = PolicySnapshot.from_mapping(CASES[1]["snapshot"])
    decision = choose(snap, TurnContextView(utterance_id="u1"))
    assert decision.chosen.kind == ActionKind.ACK_ONLY
    assert snap.background_status("mood") == "unseen"
    assert snap.required_background_goals == ("mood",)
    finished = replace(snap, thread_finished=True, thread_willing=False)
    assert (
        choose(finished, TurnContextView(utterance_id="u1")).chosen.key.label()
        == "BACKGROUND_GOAL:mood:resume"
    )


def test_snapshot_builder_reads_grounded_thread_without_mutation():
    state = EngineState(call_id="thread-builder")
    state.current_thread_label = "рассказ"
    state.thread_last_statement = "Вчера дочь приезжала, смотрели старые фотографии."
    state.thread_last_utterance_id = "u3"
    state.thread_reply_turn_id = "u3"
    state.thread_followup_count = 15
    before = copy.deepcopy(state)
    snap = build_policy_snapshot(state, TurnContextView(utterance_id="u3"))
    assert state == before
    assert snap.thread_active and snap.thread_willing and snap.thread_reply
    assert snap.thread_resume_slot == "wellness"
    assert choose(snap, TurnContextView(utterance_id="u3")).chosen.key.label() == "ACK_ONLY:listen"
    state.thread_reply_finished = True
    done = build_policy_snapshot(state, TurnContextView(utterance_id="u3"))
    assert not done.thread_willing
    assert (
        choose(done, TurnContextView(utterance_id="u3")).chosen.key.label()
        == "BACKGROUND_GOAL:wellness:resume"
    )


@pytest.mark.parametrize("status", (SlotStatus.FILLED, SlotStatus.DECLINED, SlotStatus.UNRESOLVED))
def test_terminal_wellness_does_not_become_return_question(status):
    state = EngineState(call_id="thread-terminal")
    state.current_thread_label = "рассказ"
    state.thread_last_statement = "Вчера приезжали дети."
    state.thread_last_utterance_id = "u1"
    state.slots["wellness"] = status
    snap = build_policy_snapshot(state)
    assert snap.thread_resume_slot != "wellness"


def test_stale_statement_cannot_capture_a_different_turn():
    snap = PolicySnapshot.from_mapping(CASES[1]["snapshot"])
    assert not thread_context_eligible(snap, TurnContextView(utterance_id="new"))
    assert choose(snap, TurnContextView(utterance_id="new")).chosen.thread_mode is None


def test_pending_share_obligation_cannot_be_hijacked_by_story():
    snap = PolicySnapshot.from_mapping(CASES[1]["snapshot"])
    pending = replace(snap, important_to_share_asked=True, important_to_share_resolved=False)
    assert not thread_context_eligible(pending, TurnContextView(utterance_id="u1"))
    assert choose(pending, TurnContextView(utterance_id="u1")).chosen.thread_mode is None


def test_unattributed_projection_cannot_reuse_prior_story_evidence():
    snap = PolicySnapshot.from_mapping(CASES[1]["snapshot"])
    ctx = TurnContextView(raw_text="Мне сейчас плохо")
    assert not thread_context_eligible(snap, ctx)
    assert choose(snap, ctx).chosen.thread_mode is None


def _finished_mandatory_story_state():
    state = EngineState(
        call_id="terminal-background-return",
        mandatory_background_goals=True,
        current_thread_label="рассказ",
        thread_last_statement="Дочь сегодня приезжала",
        thread_last_utterance_id="story",
        thread_reply_finished=True,
        important_to_share_resolved=True,
    )
    for slot in ("wellness", "mood", "sleep", "plans"):
        state.slots[slot] = SlotStatus.FILLED
        state.background_goal_status[slot] = "unseen"  # legacy sync has not run
    return state


@pytest.mark.parametrize("slot", ("wellness", "mood", "sleep", "plans"))
@pytest.mark.parametrize("status", (SlotStatus.FILLED, SlotStatus.DECLINED, SlotStatus.UNRESOLVED))
def test_stale_coverage_cannot_reopen_terminal_background_slot(slot, status):
    state = _finished_mandatory_story_state()
    state.slots[slot] = status
    before = copy.deepcopy(state)
    snap = build_policy_snapshot(state)
    assert state == before
    assert snap.thread_resume_slot is None
    assert snap.background_status(slot) == (
        "answered" if status == SlotStatus.FILLED else "skipped"
    )
    assert choose(snap, TurnContextView()).chosen.kind == ActionKind.SUMMARY_CLOSE
    assert state.slot_values == before.slot_values  # unknown/refusal never becomes a value


@pytest.mark.parametrize("slot", ("wellness", "mood", "sleep", "plans"))
@pytest.mark.parametrize(
    "lifecycle", ("SATISFIED", "DECLINED", "SKIPPED", "NOT_APPLICABLE", "UNCLEAR")
)
def test_goal_lifecycle_prevents_return_even_with_open_slot_and_stale_coverage(slot, lifecycle):
    from packages.dialogue_engine.state import GoalLifecycle, GoalState

    state = _finished_mandatory_story_state()
    state.slots[slot] = SlotStatus.OPEN
    state.goals[f"goal:{slot}"] = GoalState(slot=slot, lifecycle=GoalLifecycle(lifecycle))
    before = copy.deepcopy(state)
    snap = build_policy_snapshot(state)
    assert state == before and snap.thread_resume_slot is None
    assert snap.background_status(slot) == ("answered" if lifecycle == "SATISFIED" else "skipped")
    assert choose(snap, TurnContextView()).chosen.kind == ActionKind.SUMMARY_CLOSE


@pytest.mark.parametrize("slot", ("wellness", "mood", "sleep", "plans"))
@pytest.mark.parametrize("status", (SlotStatus.FILLED, SlotStatus.DECLINED, SlotStatus.UNRESOLVED))
def test_goal_slot_disposition_prevents_return_even_before_slot_projection(slot, status):
    from packages.dialogue_engine.state import GoalState

    state = _finished_mandatory_story_state()
    state.slots[slot] = SlotStatus.OPEN
    state.goals[f"goal:{slot}"] = GoalState(slot=slot, status=status)
    before = copy.deepcopy(state)
    snap = build_policy_snapshot(state)
    assert state == before and snap.thread_resume_slot is None
    assert snap.background_status(slot) == (
        "answered" if status == SlotStatus.FILLED else "skipped"
    )
    assert choose(snap, TurnContextView()).chosen.kind == ActionKind.SUMMARY_CLOSE


@pytest.mark.parametrize("mode", ("off", "shadow", "policy"))
def test_real_sdk_story_returns_to_uncovered_goal_in_mandatory_configuration(monkeypatch, mode):
    from packages.dialogue_engine.engine import DialogueEngine

    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", mode)
    monkeypatch.setenv("IMVERA_ACTION_POLICY_CUTOVER_ENABLED", "1")
    monkeypatch.setenv("IMVERA_COVERAGE_LADDER", "0")
    engine = DialogueEngine(call_id=f"mandatory-story:{mode}")
    engine.state.mandatory_background_goals = True

    def drain():
        effects = []
        while (effect := engine.pop_speak_effect()) is not None:
            effects.append(effect)
            engine.on_playout_completed(effect.generation, effect.question_id)
        return effects

    engine.start()
    assert any(effect.slot == "wellness" for effect in drain())
    for index, text in enumerate(
        (
            "Хорошо, дочь сегодня приезжала.",
            "Мы пили чай и разговаривали.",
            "Больше нечего добавить.",
        )
    ):
        turn_id = f"story:{index}"
        rich = engine.build_rich_turn(text, utterance_id=turn_id)
        engine.on_user_turn(turn_id, text, rich_turn=rich)
        effects = drain()
        assert effects
        assert engine.state.slots["wellness"] == SlotStatus.FILLED
        assert not any(effect.marks_question and effect.slot == "wellness" for effect in effects)
        if index < 2:
            assert all(not effect.marks_question for effect in effects)
        else:
            assert effects[-1].marks_question and effects[-1].slot == "mood"
            assert engine.state.slots["mood"] == SlotStatus.OPEN
    assert engine.state.action_policy_router_stats["conversation_policy_authoritative"] >= 3


@pytest.mark.parametrize("slot", ("wellness", "mood", "sleep", "plans"))
def test_blocked_goal_is_not_reclassified_as_a_terminal_outcome(slot):
    from packages.dialogue_engine.state import GoalLifecycle, GoalState

    state = _finished_mandatory_story_state()
    state.slots[slot] = SlotStatus.OPEN
    state.goals[f"goal:{slot}"] = GoalState(slot=slot, lifecycle=GoalLifecycle.BLOCKED)
    before = copy.deepcopy(state)
    snap = build_policy_snapshot(state)
    assert state == before
    assert snap.background_status(slot) == "unseen"
    assert snap.thread_resume_slot == slot
    # Existing blocked-goal owner has not produced an answer/terminal outcome.
    assert choose(snap, TurnContextView()).chosen.kind != ActionKind.SUMMARY_CLOSE
