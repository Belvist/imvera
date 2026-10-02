#!/usr/bin/env python3
"""Isolated all-core ActionPolicy differential gate (lab tooling only).

Historical v8->v9 is replayed from immutable Git bytes. The default gate compares
historical v9 with the current v10 candidate. Both run in independent subprocesses
with the same captured support tree and inputs; the live worktree is never swapped.
This is a policy/state replay, not an audio or human-conversation acceptance test.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.dialogue_engine.action_policy_shadow_config import (  # noqa: E402
    FROZEN_POLICY_SHA,
    HISTORICAL_BASELINE_SHA,
)

# Historical v8 baseline for the differential — decoupled from the runtime
# freeze pin on purpose: repinning FROZEN_POLICY_SHA to v9 must not move the
# baseline this tool diffs against.
V8_BASELINE_SHA = "c0fa158bd2ffb4109d1f0776c3b3245cdff31ce4"
V8_BASELINE_SHORT = "c0fa158"
CORE_NAMES = (
    "actions.py",
    "constraints.py",
    "features.py",
    "mandatory.py",
    "need_value.py",
    "needs.py",
    "policy.py",
    "scorer.py",
    "semantic_signals.py",
    "snapshot.py",
)
POLICY_RELS = tuple(f"packages/dialogue_engine/action_policy/{name}" for name in CORE_NAMES)
LADDER_FLAGS = ("0", "1")
EXPECTED_V9_ACTION = "ASK_EPISODE:severity"
EXPECTED_REASON = "expected-temporal-severity-retention"
EXPECTED_FRESH_REASON = "expected-fresh-issue-probe-retention"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def policy_paths() -> list[Path]:
    return [ROOT / rel for rel in POLICY_RELS]


def read_working_tree() -> dict[str, bytes]:
    return {rel: (ROOT / rel).read_bytes() for rel in POLICY_RELS}


def snapshot_hashes() -> dict[str, str]:
    return {rel: sha256_bytes((ROOT / rel).read_bytes()) for rel in POLICY_RELS}


def git_show_file(rev: str, rel: str) -> bytes:
    """Read-only git object access; never touches the working tree or index."""
    proc = subprocess.run(
        ["git", "show", f"{rev}:{rel}"],
        capture_output=True,
        check=False,
        cwd=ROOT,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git show {rev}:{rel} failed: {proc.stderr.decode()[:300]}")
    return proc.stdout


@contextmanager
def isolated_variant(payload: dict[str, bytes], support_root: Path = ROOT):
    """Disposable source copy. Never write into ROOT, even on exceptions."""
    with tempfile.TemporaryDirectory(prefix="imvera-policy-diff-") as tmp:
        isolated = Path(tmp)
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
        for name in ("packages", "scripts", "tests", "models"):
            shutil.copytree(support_root / name, isolated / name, ignore=ignore)
        tool = isolated / "tools/voice_lab/policy_diff_v8_v9.py"
        tool.parent.mkdir(parents=True)
        shutil.copyfile(support_root / "tools/voice_lab/policy_diff_v8_v9.py", tool)
        for rel, data in payload.items():
            (isolated / rel).write_bytes(data)
        yield isolated


def _run_isolated(
    payload: dict[str, bytes],
    ladders: tuple[str, ...],
    *,
    include_threads: bool,
    support_root: Path,
) -> dict[str, Any]:
    with isolated_variant(payload, support_root) as isolated:
        env = dict(
            os.environ,
            PYTHONPATH=str(isolated),
            PYTHONDONTWRITEBYTECODE="1",
            IMVERA_ACTION_POLICY_MODE="legacy",
        )
        proc = subprocess.run(
            [
                sys.executable,
                "-B",
                str(isolated / "tools/voice_lab/policy_diff_v8_v9.py"),
                "--worker",
                "--ladders",
                ",".join(ladders),
                *(["--include-threads"] if include_threads else []),
            ],
            cwd=isolated,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"isolated policy failed rc={proc.returncode}: {proc.stderr[-2000:]}"
            )
        return json.loads(proc.stdout)


def _bench_helpers() -> SimpleNamespace:
    # Importing benchmark_action_policy also imports the *current live bridge*.
    # Historical cores must not depend on a v10 enum via that unrelated module.
    from packages.contracts.enums import SlotStatus
    from packages.dialogue_engine.action_policy.actions import ActionKind
    from packages.dialogue_engine.state import BackgroundGoalCoverage

    def load_cases():
        out = []
        for split in ("development", "held_out", "p0_golden"):
            for path in sorted((ROOT / "tests/action_policy/corpus" / split).glob("*.json")):
                out.extend((split, case) for case in json.loads(path.read_text()))
        return out

    def projection(state, rich):
        for fact in rich.goal_facts:
            if fact.field in state.slots:
                state.slots[fact.field] = SlotStatus.FILLED
                state.background_goal_status[fact.field] = (
                    BackgroundGoalCoverage.COVERED_FROM_SPEECH.value
                )

    def expected(prefix):
        for p, kind in (
            ("episode_", ActionKind.ASK_EPISODE),
            ("probe_", ActionKind.CLARIFY),
            ("important_to_share_listen", ActionKind.LISTEN_META),
            ("important_to_share", ActionKind.IMPORTANT_TO_SHARE),
            ("goodbye_final", ActionKind.GOODBYE_FINAL),
            ("summary", ActionKind.SUMMARY_CLOSE),
        ):
            if prefix and prefix.startswith(p):
                return kind
        return None

    return SimpleNamespace(
        _load_cases=load_cases,
        _apply_goal_projection=projection,
        _expected_prefix_to_kind=expected,
        LIVE_REPLAY_ROOT=ROOT / "tests/live_replay/fixtures",
    )


def _snapshot_summary(snapshot: Any) -> dict[str, Any]:
    active = snapshot.active_episode
    return {
        "last_question_need": snapshot.last_question_need,
        "pending_episode_attribute": snapshot.pending_episode_attribute,
        "active_episode_id": snapshot.active_episode_id,
        "temporal_known": bool(active.temporal_known) if active else None,
        "current_known": bool(active.current_known) if active else None,
        "severity_known": bool(active.severity_known) if active else None,
    }


def _turn_context_flags(ctx: Any) -> dict[str, Any]:
    return {
        "has_new_speaker_issue": bool(getattr(ctx, "has_new_speaker_issue", False)),
        "answers_pending_question": bool(getattr(ctx, "answers_pending_question", False)),
        "user_question": bool(getattr(ctx, "user_question", False)),
    }


def _run_snapshot_rows() -> list[dict[str, Any]]:
    bench = _bench_helpers()
    policy = importlib.import_module("packages.dialogue_engine.action_policy.policy")
    snap_mod = importlib.import_module("packages.dialogue_engine.action_policy.snapshot")
    rows: list[dict[str, Any]] = []
    for split, case in bench._load_cases():
        snapshot = snap_mod.PolicySnapshot.from_mapping(case["snapshot"])
        ctx = snap_mod.TurnContextView.from_mapping(case.get("context", {}))
        try:
            decision = policy.choose(snapshot, ctx)
        except Exception as exc:  # noqa: BLE001 - record constraint blowups as rows
            rows.append(
                {
                    "scenario_id": f"snapshot:{split}:{case['id']}",
                    "battery": "snapshot",
                    "action": f"CONSTRAINT_VIOLATION:{type(exc).__name__}",
                    "rejected": [],
                    "acceptable": sorted(case.get("acceptable", ())),
                    "forbidden": sorted(case.get("forbidden", ())),
                    "snapshot_summary": _snapshot_summary(snapshot),
                    "turn_context": _turn_context_flags(ctx),
                }
            )
            continue
        rows.append(
            {
                "scenario_id": f"snapshot:{split}:{case['id']}",
                "battery": "snapshot",
                "action": decision.chosen.key.label(),
                "rejected": [
                    {"action": r.action.key.label(), "rule": r.rule_id} for r in decision.rejected
                ],
                "acceptable": sorted(case.get("acceptable", ())),
                "forbidden": sorted(case.get("forbidden", ())),
                "snapshot_summary": _snapshot_summary(snapshot),
                "turn_context": _turn_context_flags(ctx),
            }
        )
    return rows


def _run_pipeline_rows() -> list[dict[str, Any]]:
    bench = _bench_helpers()
    policy = importlib.import_module("packages.dialogue_engine.action_policy.policy")
    snap_mod = importlib.import_module("packages.dialogue_engine.action_policy.snapshot")
    state_mod = importlib.import_module("packages.dialogue_engine.state")
    turn_mod = importlib.import_module("packages.dialogue_engine.turn_understanding")
    issue_mod = importlib.import_module("packages.dialogue_engine.issue_memory")
    obs_mod = importlib.import_module("packages.dialogue_engine.semantic_kernel.observation_memory")
    rows: list[dict[str, Any]] = []
    for path in sorted(bench.LIVE_REPLAY_ROOT.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        state = state_mod.EngineState(
            call_id=f"action-policy-{raw.get('call_id', path.stem)}",
            elder_display_name=raw.get("elder_display_name", "Даниил"),
        )
        for idx, turn in enumerate(raw.get("turns", ()), start=1):
            pending_attr = turn.get("pending_episode_attribute")
            if pending_attr:
                state.pending_episode_attribute = pending_attr
            answer_slot = turn.get("answer_slot")
            if answer_slot:
                state.delivered_question = state_mod.Question(
                    question_id=f"offline-{idx}",
                    slot=answer_slot,
                    text=turn.get("bot_text", ""),
                    intent=answer_slot,
                )
                if answer_slot.startswith("probe_"):
                    state.probe_phase = answer_slot.removeprefix("probe_")
            elif pending_attr and state.active_episode_id:
                state.delivered_question = state_mod.Question(
                    question_id=f"offline-{idx}",
                    slot=f"episode_{state.active_episode_id}_{pending_attr}",
                    text=turn.get("bot_text", ""),
                    intent=f"episode_{pending_attr}",
                )
            rich = turn_mod.build_rich_turn_from_text(
                turn["stt_final"], utterance_id=f"u-{idx}", engine_state=state
            )
            rich = issue_mod.filter_rich_turn_mentions(state, rich)
            obs_mod.atomic_semantic_apply(state, rich)
            bench._apply_goal_projection(state, rich)
            state.turn_seq += 1
            snapshot = snap_mod.build_policy_snapshot(state)
            ctx = snap_mod.TurnContextView.from_turn(rich)
            decision = policy.choose(snapshot, ctx)
            expected = bench._expected_prefix_to_kind(turn.get("expected_intent_prefix"))
            if expected is None:
                continue
            rows.append(
                {
                    "scenario_id": f"pipeline:{path.stem}:turn{idx}",
                    "battery": "pipeline",
                    "action": decision.chosen.key.label(),
                    "rejected": [
                        {"action": r.action.key.label(), "rule": r.rule_id}
                        for r in decision.rejected
                    ],
                    "expected_kind": expected.value,
                    "pending_episode_attribute": pending_attr,
                    "snapshot_summary": _snapshot_summary(snapshot),
                    "turn_context": _turn_context_flags(ctx),
                }
            )
    return rows


def _run_thread_rows() -> list[dict[str, Any]]:
    from packages.dialogue_engine.action_policy.policy import choose
    from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView

    cases = json.loads(
        (ROOT / "tests/action_policy/corpus/conversation_v10/scenarios.json").read_text()
    )
    rows = []
    for case in cases:
        snap = PolicySnapshot.from_mapping(case["snapshot"])
        ctx = TurnContextView.from_mapping(case["context"])
        decision = choose(snap, ctx)
        rows.append(
            {
                "scenario_id": f"thread:{case['id']}",
                "battery": "conversation_v10",
                "action": decision.chosen.key.label(),
                "rejected": [
                    {"action": x.action.key.label(), "rule": x.rule_id} for x in decision.rejected
                ],
                "snapshot_summary": _snapshot_summary(snap),
                "turn_context": _turn_context_flags(ctx),
                "expected_v10_action": case.get("expected_v10_action"),
                "expected_delta": case["expected_delta"],
            }
        )
    return rows


def run_battery_once(ladder: str, *, include_threads: bool = False) -> list[dict[str, Any]]:
    previous = os.environ.get("IMVERA_COVERAGE_LADDER")
    os.environ["IMVERA_COVERAGE_LADDER"] = ladder
    try:
        rows = _run_snapshot_rows() + _run_pipeline_rows()
        if include_threads:
            rows += _run_thread_rows()
    finally:
        if previous is None:
            os.environ.pop("IMVERA_COVERAGE_LADDER", None)
        else:
            os.environ["IMVERA_COVERAGE_LADDER"] = previous
    for row in rows:
        row["ladder"] = ladder
    return rows


def _is_expected_temporal_severity(v8: dict[str, Any], v9: dict[str, Any]) -> bool:
    if v9["action"] != EXPECTED_V9_ACTION or v8["action"] == EXPECTED_V9_ACTION:
        return False
    for side in (v9.get("snapshot_summary", {}), v8.get("snapshot_summary", {})):
        if (
            side.get("last_question_need") == "temporal"
            and side.get("temporal_known") is True
            and side.get("current_known") is True
            and side.get("severity_known") is False
        ):
            return True
    return False


def _is_expected_fresh_issue_probe(v8: dict[str, Any], v9: dict[str, Any]) -> bool:
    # snapshot.py guard (fs-1f6d3000): a brand-new speaker episode this turn
    # blocks transition so the fresh lead is probed (ASK severity) instead of
    # dropped. Checked AFTER the temporal pattern: a temporal retention case
    # may also carry a fresh issue, and keeps the temporal reason.
    if v9["action"] != EXPECTED_V9_ACTION or v8["action"] == EXPECTED_V9_ACTION:
        return False
    summary = v9.get("snapshot_summary", {})
    context = v9.get("turn_context", {})
    return bool(
        context.get("has_new_speaker_issue") is True
        and summary.get("severity_known") is False
        and summary.get("active_episode_id")
    )


def classify(v8: dict[str, Any], v9: dict[str, Any]) -> str:
    if v8["action"] == v9["action"]:
        return "identical"
    if _is_expected_temporal_severity(v8, v9):
        return EXPECTED_REASON
    if _is_expected_fresh_issue_probe(v8, v9):
        return EXPECTED_FRESH_REASON
    return "unexplained"


def compare_runs(
    v8_rows: list[dict[str, Any]], v9_rows: list[dict[str, Any]], *, comparison: str = "v8-v9"
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_key_v8 = {(r["ladder"], r["scenario_id"]): r for r in v8_rows}
    by_key_v9 = {(r["ladder"], r["scenario_id"]): r for r in v9_rows}
    if set(by_key_v8) != set(by_key_v9):
        missing = sorted(set(by_key_v8) ^ set(by_key_v9))
        raise RuntimeError(f"battery key mismatch between variants: {missing[:5]}")
    entries: list[dict[str, Any]] = []
    for key in sorted(by_key_v8):
        ladder, scenario_id = key
        v8, v9 = by_key_v8[key], by_key_v9[key]
        reason = (
            classify(v8, v9)
            if comparison == "v8-v9"
            else (
                "identical"
                if v8["action"] == v9["action"]
                else "expected-user-led-thread-move"
                if v9.get("expected_delta") and v9["action"] == v9.get("expected_v10_action")
                else "unexplained"
            )
        )
        entries.append(
            {
                "scenario_id": scenario_id,
                "ladder": ladder,
                "battery": v9.get("battery"),
                "v8_action": v8["action"],
                "v9_action": v9["action"],
                "baseline_action": v8["action"],
                "candidate_action": v9["action"],
                "expected_candidate_action": v9.get("expected_v10_action"),
                "same": v8["action"] == v9["action"],
                "v8_constraints": v8["rejected"],
                "v9_constraints": v9["rejected"],
                "reason_for_difference": reason,
                "snapshot_summary": v9.get("snapshot_summary"),
                "turn_context": v9.get("turn_context"),
            }
        )
    changed = [e for e in entries if not e["same"]]
    return entries, changed


def run_full_comparison(
    ladders: tuple[str, ...] = LADDER_FLAGS, *, comparison: str = "v9-v10"
) -> dict[str, Any]:
    """Capture support sources once and replay all ten core files in subprocesses."""
    if comparison not in {"v8-v9", "v9-v10"}:
        raise ValueError(f"unknown comparison: {comparison}")
    hashes_before = snapshot_hashes()
    baseline_sha = V8_BASELINE_SHA if comparison == "v8-v9" else HISTORICAL_BASELINE_SHA
    baseline = {rel: git_show_file(baseline_sha, rel) for rel in POLICY_RELS}
    candidate = (
        {rel: git_show_file(HISTORICAL_BASELINE_SHA, rel) for rel in POLICY_RELS}
        if comparison == "v8-v9"
        else read_working_tree()
    )
    if comparison == "v9-v10" and FROZEN_POLICY_SHA is not None:
        pinned = {rel: git_show_file(FROZEN_POLICY_SHA, rel) for rel in POLICY_RELS}
        if pinned != candidate:
            raise RuntimeError("active pinned core differs from working-tree candidate")
    # Freeze the non-core envelope for both workers as well. A concurrent source
    # edit cannot create a mixed envelope between baseline and candidate runs.
    with tempfile.TemporaryDirectory(prefix="imvera-policy-support-") as tmp:
        support = Path(tmp)
        for name in ("packages", "scripts", "tests", "models"):
            shutil.copytree(
                ROOT / name, support / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
            )
        tool = support / "tools/voice_lab/policy_diff_v8_v9.py"
        tool.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "tools/voice_lab/policy_diff_v8_v9.py", tool)
        support_hashes = {
            str(path.relative_to(support)): sha256_bytes(path.read_bytes())
            for path in sorted(support.rglob("*"))
            if path.is_file() and str(path.relative_to(support)) not in POLICY_RELS
        }
        base_run = _run_isolated(
            baseline, ladders, include_threads=comparison == "v9-v10", support_root=support
        )
        cand_run = _run_isolated(
            candidate, ladders, include_threads=comparison == "v9-v10", support_root=support
        )
    entries, changed = compare_runs(base_run["rows"], cand_run["rows"], comparison=comparison)
    expected = [e for e in changed if e["reason_for_difference"].startswith("expected-")]
    unexplained = [e for e in changed if e["reason_for_difference"] == "unexplained"]
    failed_expectations = [
        e
        for e in entries
        if e["expected_candidate_action"]
        and e["candidate_action"] != e["expected_candidate_action"]
    ]
    failures = [
        e
        for e in entries
        if any(
            a.startswith("CONSTRAINT_VIOLATION")
            for a in (e["baseline_action"], e["candidate_action"])
        )
    ]
    hashes_after = snapshot_hashes()
    return {
        "comparison": comparison,
        "isolation": "all-ten-core-files/independent-subprocesses",
        "frozen_policy_sha": FROZEN_POLICY_SHA,
        "historical_baseline_sha": HISTORICAL_BASELINE_SHA,
        "baseline_sha": baseline_sha,
        "candidate_sha": HISTORICAL_BASELINE_SHA if comparison == "v8-v9" else FROZEN_POLICY_SHA,
        "baseline_policy_version": base_run["policy_version"],
        "candidate_policy_version": cand_run["policy_version"],
        "support_tree_sha256": sha256_bytes(json.dumps(support_hashes, sort_keys=True).encode()),
        "file_hashes_before": hashes_before,
        "file_hashes_after": hashes_after,
        "files_restored": hashes_after == hashes_before,
        "working_tree_untouched": hashes_after == hashes_before,
        "baseline_file_hashes": {rel: sha256_bytes(data) for rel, data in baseline.items()},
        "candidate_file_hashes": {rel: sha256_bytes(data) for rel, data in candidate.items()},
        "ladders": list(ladders),
        "battery_sizes": {
            "baseline_rows": len(base_run["rows"]),
            "candidate_rows": len(cand_run["rows"]),
        },
        "total_compared": len(entries),
        "changed_count": len(changed),
        "expected_count": len(expected),
        "unexplained_count": len(unexplained),
        "failed_expectations": failed_expectations,
        "constraint_failures": failures,
        "gate_pass": bool(expected)
        and not unexplained
        and not failed_expectations
        and not failures
        and hashes_before == hashes_after,
        "rows": entries,
        "changed": changed,
    }


def _git_readonly(args: list[str]) -> str:
    proc = subprocess.run(args, capture_output=True, check=False, cwd=ROOT, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def default_output_path() -> Path:
    candidate = ROOT / ".run" / "policy_diff_v8_v9.json"
    proc = subprocess.run(
        ["git", "check-ignore", "-q", str(candidate)],
        check=False,
        cwd=ROOT,
    )
    if proc.returncode == 0:
        return candidate
    return ROOT / "tools" / "voice_lab" / "policy_diff_v8_v9.report.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=None, help="report file path")
    parser.add_argument("--stdout-only", action="store_true", help="skip file write")
    parser.add_argument("--comparison", choices=("v8-v9", "v9-v10"), default="v9-v10")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ladders", default="0,1", help=argparse.SUPPRESS)
    parser.add_argument("--include-threads", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        from packages.dialogue_engine.action_policy.scorer import POLICY_VERSION

        rows = []
        for ladder in args.ladders.split(","):
            rows.extend(run_battery_once(ladder, include_threads=args.include_threads))
        print(json.dumps({"policy_version": POLICY_VERSION, "rows": rows}, ensure_ascii=False))
        return 0

    try:
        report = run_full_comparison(comparison=args.comparison)
    except Exception as exc:  # noqa: BLE001 - loud failure, never silent
        print(f"POLICY_DIFF FATAL: {exc}", file=sys.stderr)
        return 2
    report["meta"] = {
        "head_sha": _git_readonly(["git", "rev-parse", "HEAD"]),
        "branch": _git_readonly(["git", "branch", "--show-current"]),
        "generated_utc": datetime.datetime.now(datetime.UTC).isoformat(),
    }

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if not args.stdout_only:
        out = Path(args.output) if args.output else default_output_path()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"POLICY_DIFF report: {out}", file=sys.stderr)

    if not report["files_restored"]:
        print("POLICY_DIFF FATAL: working-tree restore mismatch", file=sys.stderr)
        return 2
    if not report["gate_pass"]:
        print(
            "POLICY_DIFF GATE FAIL: "
            f"changed={report['changed_count']} "
            f"expected={report['expected_count']} "
            f"unexplained={report['unexplained_count']}",
            file=sys.stderr,
        )
        return 1
    print(
        "POLICY_DIFF GATE PASS: "
        f"changed={report['changed_count']} "
        f"expected={report['expected_count']} unexplained=0",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
