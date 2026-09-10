#!/usr/bin/env python3
"""Offline ActionPolicy benchmark. No production hook, no network calls."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.action_policy.actions import ActionKind, PolicyConstraintViolation
from packages.dialogue_engine.action_policy.bridge import legacy_plan_to_action_key, to_response_plan
from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.scorer import POLICY_VERSION
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView, build_policy_snapshot
from packages.dialogue_engine.conversation_policy import TurnContext, schedule_next_action
from packages.dialogue_engine.issue_memory import filter_rich_turn_mentions
from packages.dialogue_engine.semantic_kernel.observation_memory import atomic_semantic_apply
from packages.dialogue_engine.state import BackgroundGoalCoverage, CheckPath, EngineState, IssueEpisode, Question
from packages.dialogue_engine.turn_understanding import RichUserTurn, build_rich_turn_from_text

CORPUS_ROOT = ROOT / "tests" / "action_policy" / "corpus"
LIVE_REPLAY_ROOT = ROOT / "tests" / "live_replay" / "fixtures"


def _load_cases() -> list[tuple[str, dict[str, Any]]]:
    out = []
    for split in ("development", "held_out", "p0_golden"):
        for path in sorted((CORPUS_ROOT / split).glob("*.json")):
            for item in json.loads(path.read_text(encoding="utf-8")):
                out.append((split, item))
    return out


def _rich_from_ctx(ctx: TurnContextView) -> RichUserTurn:
    return RichUserTurn(
        utterance_id="bench-turn",
        raw_text=ctx.raw_text,
        dialogue_act=ctx.dialogue_act,
        control=ctx.control,
        answers_pending_question=ctx.answers_pending_question,
        needs_clarification=ctx.needs_clarification,
        user_question="user-question" if ctx.user_question else None,
        goal_facts=(),
        issue_mentions=(),
        correction=ctx.correction,
    )


def _legacy_state_from_snapshot(snapshot: PolicySnapshot) -> EngineState:
    state = EngineState(call_id="action-policy-bench")
    state.turn_seq = snapshot.turn_number
    state.active_episode_id = snapshot.active_episode_id
    state.pending_episode_ids = list(snapshot.pending_episode_ids)
    state.pending_episode_attribute = snapshot.pending_episode_attribute
    state.important_to_share_asked = snapshot.important_to_share_asked
    state.important_to_share_resolved = snapshot.important_to_share_resolved
    state.required_background_goals = set(snapshot.required_background_goals)
    state.mandatory_background_goals = snapshot.mandatory_background_goals
    state.probe_phase = snapshot.probe_phase
    if snapshot.risk_level == "urgent":
        state.check_path = CheckPath.URGENT
    for key, value in snapshot.background_goal_status:
        state.background_goal_status[key] = value
    if snapshot.wellness_entry_covered:
        state.slots["wellness"] = SlotStatus.FILLED
        state.background_goal_status["wellness"] = BackgroundGoalCoverage.ANSWERED.value
    for ep in snapshot.episodes:
        state.issue_episodes[ep.episode_id] = IssueEpisode(
            episode_id=ep.episode_id,
            primary_label="generic issue",
            kind=ep.kind,
            known_attributes=dict(ep.known_attributes),
            status=ep.status,
        )
    if snapshot.last_question_id:
        state.delivered_question = Question(
            question_id=snapshot.last_question_id,
            slot=snapshot.last_question_slot or "wellness",
            text="benchmark question",
            intent=snapshot.last_question_intent or "",
        )
    return state


def _legacy_action(snapshot: PolicySnapshot, ctx: TurnContextView) -> str:
    state = _legacy_state_from_snapshot(snapshot).model_copy(deep=True)
    turn = _rich_from_ctx(ctx)
    plan = schedule_next_action(
        state,
        TurnContext(turn=turn, user_text=ctx.raw_text, answer_slot=snapshot.last_question_slot),
    )
    return legacy_plan_to_action_key(plan).label()


def run_snapshot_benchmark() -> dict[str, Any]:
    rows = []
    split_stats: dict[str, dict[str, int]] = {}
    for split, case in _load_cases():
        snapshot = PolicySnapshot.from_mapping(case["snapshot"])
        ctx = TurnContextView.from_mapping(case.get("context", {}))
        try:
            decision = choose(snapshot, ctx)
        except PolicyConstraintViolation as exc:
            rows.append({
                "split": split,
                "id": case["id"],
                "new": f"CONSTRAINT_VIOLATION:{exc.mandatory_class}",
                "legacy": _legacy_action(snapshot, ctx),
                "acceptable": sorted(case.get("acceptable", ())),
                "forbidden": sorted(case.get("forbidden", ())),
                "new_ok": False,
                "legacy_ok": False,
                "constraint_violation": exc.mandatory_class,
            })
            stat = split_stats.setdefault(split, {"total": 0, "new_ok": 0, "legacy_ok": 0, "new_forbidden": 0, "legacy_forbidden": 0})
            stat["total"] += 1
            continue
        new_key = decision.chosen.key.label()
        legacy_key = _legacy_action(snapshot, ctx)
        acceptable = set(case.get("acceptable", ()))
        forbidden = set(case.get("forbidden", ()))
        new_ok = new_key in acceptable and new_key not in forbidden
        legacy_ok = legacy_key in acceptable and legacy_key not in forbidden
        stat = split_stats.setdefault(split, {"total": 0, "new_ok": 0, "legacy_ok": 0, "new_forbidden": 0, "legacy_forbidden": 0})
        stat["total"] += 1
        stat["new_ok"] += int(new_ok)
        stat["legacy_ok"] += int(legacy_ok)
        stat["new_forbidden"] += int(new_key in forbidden)
        stat["legacy_forbidden"] += int(legacy_key in forbidden)
        rows.append({
            "split": split,
            "id": case["id"],
            "new": new_key,
            "legacy": legacy_key,
            "acceptable": sorted(acceptable),
            "forbidden": sorted(forbidden),
            "new_ok": new_ok,
            "legacy_ok": legacy_ok,
            "rejected": [{"action": r.action.key.label(), "rule": r.rule_id} for r in decision.rejected],
            "chosen_contributions": decision.candidates[0].contributions,
        })
    return {"policy_version": POLICY_VERSION, "splits": split_stats, "cases": rows}


def _apply_goal_projection(state: EngineState, rich: RichUserTurn) -> None:
    for fact in rich.goal_facts:
        if fact.field not in state.slots:
            continue
        state.slots[fact.field] = SlotStatus.FILLED
        state.background_goal_status[fact.field] = BackgroundGoalCoverage.COVERED_FROM_SPEECH.value


def _expected_prefix_to_kind(prefix: str | None) -> ActionKind | None:
    if not prefix:
        return None
    if prefix.startswith("episode_"):
        return ActionKind.ASK_EPISODE
    if prefix.startswith("probe_concern"):
        return ActionKind.CLARIFY
    if prefix.startswith("important_to_share_listen"):
        return ActionKind.LISTEN_META
    if prefix.startswith("important_to_share"):
        return ActionKind.IMPORTANT_TO_SHARE
    if prefix.startswith("goodbye_final"):
        return ActionKind.GOODBYE_FINAL
    if prefix.startswith("summary"):
        return ActionKind.SUMMARY_CLOSE
    return None


def run_pipeline_diagnostic() -> dict[str, Any]:
    """SK -> filter -> atomic apply -> snapshot -> ActionPolicy, without production scheduler."""
    results = []
    nlu_state_loss = 0
    policy_failure = 0
    checked = 0
    for path in sorted(LIVE_REPLAY_ROOT.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        state = EngineState(call_id=f"action-policy-{raw.get('call_id', path.stem)}", elder_display_name=raw.get("elder_display_name", "Даниил"))
        for idx, turn in enumerate(raw.get("turns", ()), start=1):
            answer_slot = turn.get("answer_slot")
            if answer_slot:
                state.delivered_question = Question(
                    question_id=f"offline-{idx}",
                    slot=answer_slot,
                    text=turn.get("bot_text", ""),
                    intent=answer_slot,
                )
                if answer_slot.startswith("probe_"):
                    state.probe_phase = answer_slot.removeprefix("probe_")
            rich = build_rich_turn_from_text(turn["stt_final"], utterance_id=f"u-{idx}", engine_state=state)
            rich = filter_rich_turn_mentions(state, rich)
            before_episode_ids = set(state.issue_episodes)
            atomic_semantic_apply(state, rich)
            _apply_goal_projection(state, rich)
            state.turn_seq += 1
            snapshot = build_policy_snapshot(state)
            ctx = TurnContextView.from_turn(rich)
            decision = choose(snapshot, ctx)
            expected_kind = _expected_prefix_to_kind(turn.get("expected_intent_prefix"))
            if expected_kind is None:
                continue
            checked += 1
            state_loss = False
            if expected_kind == ActionKind.ASK_EPISODE:
                new_ids = set(state.issue_episodes) - before_episode_ids
                state_loss = not bool(new_ids or snapshot.attention_episodes)
            if state_loss:
                nlu_state_loss += 1
            elif decision.chosen.kind != expected_kind:
                policy_failure += 1
            results.append({
                "fixture": path.stem,
                "turn": idx,
                "text": turn["stt_final"],
                "expected_kind": expected_kind.value,
                "chosen": decision.chosen.key.label(),
                "nlu_state_loss": state_loss,
                "policy_failure": (not state_loss and decision.chosen.kind != expected_kind),
            })
    return {"checked_turns": checked, "nlu_state_loss": nlu_state_loss, "policy_failure": policy_failure, "turns": results}


def _percentile(sorted_ns: list[int], q: float) -> float:
    if not sorted_ns:
        return 0.0
    index = min(len(sorted_ns) - 1, max(0, int(round((len(sorted_ns) - 1) * q))))
    return sorted_ns[index] / 1_000_000.0


def run_latency(iterations: int) -> dict[str, Any]:
    state = EngineState(call_id="action-policy-latency")
    ep = IssueEpisode(
        episode_id="ep-latency",
        primary_label="generic issue",
        kind="symptom",
        known_attributes={"onset": "yesterday"},
        status="open",
    )
    state.issue_episodes[ep.episode_id] = ep
    state.active_episode_id = ep.episode_id
    state.slots["wellness"] = SlotStatus.FILLED
    state.background_goal_status["wellness"] = BackgroundGoalCoverage.ANSWERED.value
    ctx = TurnContextView(raw_text="benchmark", answers_pending_question=True)

    for _ in range(2000):
        snap = build_policy_snapshot(state)
        decision = choose(snap, ctx)
        to_response_plan(decision, snap)

    samples = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        snap = build_policy_snapshot(state)
        decision = choose(snap, ctx)
        to_response_plan(decision, snap)
        samples.append(time.perf_counter_ns() - started)
    samples.sort()
    return {
        "iterations": iterations,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "policy_version": POLICY_VERSION,
        "p50_ms": _percentile(samples, 0.50),
        "p95_ms": _percentile(samples, 0.95),
        "p99_ms": _percentile(samples, 0.99),
        "mean_ms": statistics.fmean(samples) / 1_000_000.0,
        "target_p99_ms": 10.0,
        "target_pass": _percentile(samples, 0.99) < 10.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = {
        "snapshot_benchmark": run_snapshot_benchmark(),
        "pipeline_diagnostic": run_pipeline_diagnostic(),
        "latency": run_latency(args.iterations),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report["snapshot_benchmark"]["splits"], ensure_ascii=False, indent=2))
        print(json.dumps(report["pipeline_diagnostic"], ensure_ascii=False, indent=2))
        print(json.dumps(report["latency"], ensure_ascii=False, indent=2))

    splits = report["snapshot_benchmark"]["splits"]
    p0 = splits.get("p0_golden", {})
    held = splits.get("held_out", {})
    p0_ok = bool(p0.get("total", 0)) and p0.get("new_ok") == p0.get("total") and p0.get("new_forbidden") == 0
    held_ratio = (held.get("new_ok", 0) / held.get("total", 1)) if held.get("total") else 0.0
    held_ok = held_ratio >= 0.95 and held.get("new_forbidden") == 0
    latency_ok = bool(report["latency"]["target_pass"])
    pipeline = report["pipeline_diagnostic"]
    pipeline_ok = pipeline["policy_failure"] == 0 and pipeline["nlu_state_loss"] == 0
    return 0 if p0_ok and held_ok and latency_ok and pipeline_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
