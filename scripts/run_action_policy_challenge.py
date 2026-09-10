#!/usr/bin/env python3
"""Run frozen ActionPolicy challenge corpus exactly once; no tuning."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.dialogue_engine.action_policy.actions import PolicyConstraintViolation
from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.scorer import POLICY_VERSION
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView

CHALLENGE_PATH = ROOT / "tests" / "action_policy" / "corpus" / "challenge_frozen" / "scenarios.json"
FROZEN_POLICY_SHA = "0271c624e93e3f8e6f01d5f6dafcf03a377c8b8b"
FREEZE_MANIFEST_SHA = "639babcc13c69ee498bbe7a9700f7362a7586808"


def _load_cases() -> list[dict[str, Any]]:
    return json.loads(CHALLENGE_PATH.read_text(encoding="utf-8"))


def _scored_row(item) -> dict[str, Any]:
    return {
        "action": item.action.key.label(),
        "score": item.score,
        "contributions": item.contributions,
        "features": item.features,
    }


def run_challenge() -> dict[str, Any]:
    cases = _load_cases()
    rows: list[dict[str, Any]] = []
    passed = 0
    failed = 0
    forbidden_count = 0
    constraint_violation_count = 0
    p0_like_failures = 0
    p0_like_total = 0

    for case in cases:
        snapshot = PolicySnapshot.from_mapping(case["snapshot"])
        ctx = TurnContextView.from_mapping(case.get("context", {}))
        acceptable = set(case.get("acceptable", ()))
        forbidden = set(case.get("forbidden", ()))
        is_p0_like = case["id"].startswith(("ch_safety", "ch_no_ack", "ch_no_premature", "ch_no_repeat"))

        try:
            decision = choose(snapshot, ctx)
            chosen = decision.chosen.key.label()
            violation = False
            rejections = [
                {"action": r.action.key.label(), "rule_id": r.rule_id, "reason": r.reason}
                for r in decision.rejected
            ]
            candidates = [_scored_row(item) for item in decision.candidates]
        except PolicyConstraintViolation as exc:
            constraint_violation_count += 1
            chosen = f"CONSTRAINT_VIOLATION:{exc.mandatory_class}"
            violation = True
            rejections = [
                {"action": r.action.key.label(), "rule_id": r.rule_id, "reason": r.reason}
                for r in exc.rejected
            ]
            candidates = []

        ok = chosen in acceptable and chosen not in forbidden and not violation
        if chosen in forbidden:
            forbidden_count += 1
        if ok:
            passed += 1
        else:
            failed += 1
        if is_p0_like:
            p0_like_total += 1
            if not ok:
                p0_like_failures += 1

        rows.append(
            {
                "id": case["id"],
                "chosen": chosen,
                "acceptable": sorted(acceptable),
                "forbidden": sorted(forbidden),
                "pass": ok,
                "constraint_violation": violation,
                "rejections": rejections,
                "candidates": candidates,
            }
        )

    total = len(cases)
    return {
        "frozen_policy_sha": FROZEN_POLICY_SHA,
        "freeze_manifest_commit": FREEZE_MANIFEST_SHA,
        "challenge_corpus_commit": None,
        "policy_version": POLICY_VERSION,
        "corpus_path": str(CHALLENGE_PATH.relative_to(ROOT)),
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / total if total else 0.0,
        "forbidden_count": forbidden_count,
        "constraint_violation_count": constraint_violation_count,
        "p0_like_total": p0_like_total,
        "p0_like_passed": p0_like_total - p0_like_failures,
        "p0_like_pass_rate": (
            (p0_like_total - p0_like_failures) / p0_like_total if p0_like_total else 1.0
        ),
        "pass_criteria": {
            "forbidden_count": 0,
            "constraint_violation_count": 0,
            "p0_like_pass_rate": 1.0,
            "overall_pass_rate_min": 0.95,
        },
        "passed_gate": (
            forbidden_count == 0
            and constraint_violation_count == 0
            and p0_like_failures == 0
            and passed / total >= 0.95
        ),
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(ROOT / "docs/evaluation/action-policy-phase1-v5-challenge.json"),
    )
    parser.add_argument("--challenge-sha", default="")
    args = parser.parse_args()

    report = run_challenge()
    if args.challenge_sha:
        report["challenge_corpus_commit"] = args.challenge_sha
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(
        {
            "passed_gate": report["passed_gate"],
            "passed": report["passed"],
            "failed": report["failed"],
            "forbidden_count": report["forbidden_count"],
            "constraint_violation_count": report["constraint_violation_count"],
            "pass_rate": report["pass_rate"],
            "output": str(out.relative_to(ROOT)),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0 if report["passed_gate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
