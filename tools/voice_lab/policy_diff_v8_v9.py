#!/usr/bin/env python3
"""ActionPolicy v8 <-> v9 differential evaluator (lab tooling, NOT prod).

Step 1 of the owner-approved v9 candidate acceptance process: differential
BEFORE any freeze. Compares the v8 baseline (FROZEN_POLICY_SHA files) against
the v9 candidate (current working-tree policy files) over the existing
dialogue/policy battery, twice per ladder flag value.

- v8 bytes are read via ``git show <sha>:<path>`` (never touches git index).
- v9 bytes are the pre-run working-tree content, held in memory.
- SHA256 snapshots before/after; LOUD nonzero failure if restore mismatches.
- Report: JSON to stdout + file (``.run/`` when gitignored, else lab fallback).
- Gate: the ONLY systematic difference class may be the temporal->severity
  retention; any unexplained diff (or zero expected diffs) exits nonzero.

Expected single behavioral delta: after a just-obtained temporal fact with
severity still unknown, v9 keeps severity information value -> ASK severity
(no conversation-wide reshuffles).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.dialogue_engine.action_policy_shadow_config import (  # noqa: E402
    FROZEN_POLICY_SHA,
)

# Historical v8 baseline for the differential — decoupled from the runtime
# freeze pin on purpose: repinning FROZEN_POLICY_SHA to v9 must not move the
# baseline this tool diffs against.
V8_BASELINE_SHA = "c0fa158bd2ffb4109d1f0776c3b3245cdff31ce4"
V8_BASELINE_SHORT = "c0fa158"
POLICY_RELS = (
    "packages/dialogue_engine/action_policy/need_value.py",
    "packages/dialogue_engine/action_policy/snapshot.py",
)
LADDER_FLAGS = ("0", "1")
EXPECTED_V9_ACTION = "ASK_EPISODE:severity"
EXPECTED_REASON = "expected-temporal-severity-retention"
EXPECTED_FRESH_REASON = "expected-fresh-issue-probe-retention"

_PURGE_PREFIXES = (
    "packages.dialogue_engine.action_policy",
    "scripts.benchmark_action_policy",
)


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


def purge_policy_modules() -> None:
    for name in [n for n in sys.modules if n.partition(".")[0] in {"packages", "scripts"}]:
        if name == "packages.dialogue_engine.action_policy_shadow_config":
            continue
        if name in _PURGE_PREFIXES or name.startswith(_PURGE_PREFIXES):
            del sys.modules[name]
    importlib.invalidate_caches()


def install_variant(variant: str, v8: dict[str, bytes], v9: dict[str, bytes]) -> None:
    payload = {"v8": v8, "v9": v9}[variant]
    for rel, data in payload.items():
        (ROOT / rel).write_bytes(data)
    purge_policy_modules()


@contextmanager
def variant_installed(variant: str, v8: dict[str, bytes], v9: dict[str, bytes]):
    install_variant(variant, v8, v9)
    try:
        yield
    finally:
        install_variant("v9", v8, v9)


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
    bench = importlib.import_module("scripts.benchmark_action_policy")
    policy = importlib.import_module("packages.dialogue_engine.action_policy.policy")
    snap_mod = importlib.import_module("packages.dialogue_engine.action_policy.snapshot")
    rows: list[dict[str, Any]] = []
    for split, case in bench._load_cases():
        snapshot = snap_mod.PolicySnapshot.from_mapping(case["snapshot"])
        ctx = snap_mod.TurnContextView.from_mapping(case.get("context", {}))
        try:
            decision = policy.choose(snapshot, ctx)
        except Exception as exc:  # noqa: BLE001 - record constraint blowups as rows
            rows.append({
                "scenario_id": f"snapshot:{split}:{case['id']}",
                "battery": "snapshot",
                "action": f"CONSTRAINT_VIOLATION:{type(exc).__name__}",
                "rejected": [],
                "acceptable": sorted(case.get("acceptable", ())),
                "forbidden": sorted(case.get("forbidden", ())),
                "snapshot_summary": _snapshot_summary(snapshot),
                "turn_context": _turn_context_flags(ctx),
            })
            continue
        rows.append({
            "scenario_id": f"snapshot:{split}:{case['id']}",
            "battery": "snapshot",
            "action": decision.chosen.key.label(),
            "rejected": [
                {"action": r.action.key.label(), "rule": r.rule_id}
                for r in decision.rejected
            ],
            "acceptable": sorted(case.get("acceptable", ())),
            "forbidden": sorted(case.get("forbidden", ())),
            "snapshot_summary": _snapshot_summary(snapshot),
            "turn_context": _turn_context_flags(ctx),
        })
    return rows


def _run_pipeline_rows() -> list[dict[str, Any]]:
    bench = importlib.import_module("scripts.benchmark_action_policy")
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
            rows.append({
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
            })
    return rows


def run_battery_once(ladder: str) -> list[dict[str, Any]]:
    previous = os.environ.get("IMVERA_COVERAGE_LADDER")
    os.environ["IMVERA_COVERAGE_LADDER"] = ladder
    try:
        rows = _run_snapshot_rows() + _run_pipeline_rows()
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
    v8_rows: list[dict[str, Any]], v9_rows: list[dict[str, Any]]
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
        reason = classify(v8, v9)
        entries.append({
            "scenario_id": scenario_id,
            "ladder": ladder,
            "battery": v9.get("battery"),
            "v8_action": v8["action"],
            "v9_action": v9["action"],
            "same": v8["action"] == v9["action"],
            "v8_constraints": v8["rejected"],
            "v9_constraints": v9["rejected"],
            "reason_for_difference": reason,
            "snapshot_summary": v9.get("snapshot_summary"),
            "turn_context": v9.get("turn_context"),
        })
    changed = [e for e in entries if not e["same"]]
    return entries, changed


def run_full_comparison(ladders: tuple[str, ...] = LADDER_FLAGS) -> dict[str, Any]:
    """Swap v8 in, run battery, restore v9, run battery. Always restores v9."""
    if not V8_BASELINE_SHA.startswith(V8_BASELINE_SHORT):
        raise RuntimeError(f"v8 baseline drift: {V8_BASELINE_SHA}")
    v9 = read_working_tree()
    v8 = {rel: git_show_file(V8_BASELINE_SHA, rel) for rel in POLICY_RELS}
    hashes_before = {rel: sha256_bytes(data) for rel, data in v9.items()}
    v8_rows: list[dict[str, Any]] = []
    v9_rows: list[dict[str, Any]] = []
    try:
        with variant_installed("v8", v8, v9):
            for ladder in ladders:
                v8_rows.extend(run_battery_once(ladder))
        for ladder in ladders:  # v9 restored by context exit
            v9_rows.extend(run_battery_once(ladder))
    finally:
        install_variant("v9", v8, v9)
    hashes_after = snapshot_hashes()
    entries, changed = compare_runs(v8_rows, v9_rows)
    expected = [
        e for e in changed
        if e["reason_for_difference"] in (EXPECTED_REASON, EXPECTED_FRESH_REASON)
    ]
    unexplained = [e for e in changed if e["reason_for_difference"] == "unexplained"]
    gate_pass = not unexplained and bool(expected)
    return {
        "frozen_policy_sha": FROZEN_POLICY_SHA,
        "v8_baseline_sha": V8_BASELINE_SHA,
        "v9_candidate": "working-tree need_value.py + snapshot.py",
        "file_hashes_before": hashes_before,
        "file_hashes_after": hashes_after,
        "files_restored": hashes_after == hashes_before,
        "v8_file_hashes": {rel: sha256_bytes(data) for rel, data in v8.items()},
        "v9_file_hashes": {rel: sha256_bytes(data) for rel, data in v9.items()},
        "ladders": list(ladders),
        "battery_sizes": {"v8_rows": len(v8_rows), "v9_rows": len(v9_rows)},
        "total_compared": len(entries),
        "changed_count": len(changed),
        "expected_count": len(expected),
        "unexplained_count": len(unexplained),
        "gate_pass": gate_pass,
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
    args = parser.parse_args(argv)

    try:
        report = run_full_comparison()
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
