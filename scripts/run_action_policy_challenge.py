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

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.action_policy.actions import PolicyConstraintViolation
from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.scorer import POLICY_VERSION
from packages.dialogue_engine.action_policy.snapshot import (
    PolicySnapshot,
    TurnContextView,
    build_policy_snapshot,
)
from packages.dialogue_engine.state import EngineState, IssueEpisode, Question

CORPUS_CHOICES = {
    "challenge_frozen": ROOT
    / "tests"
    / "action_policy"
    / "corpus"
    / "challenge_frozen"
    / "scenarios.json",
    "challenge_v6_frozen": ROOT
    / "tests"
    / "action_policy"
    / "corpus"
    / "challenge_v6_frozen"
    / "scenarios.json",
    "challenge_v7_frozen": ROOT
    / "tests"
    / "action_policy"
    / "corpus"
    / "challenge_v7_frozen"
    / "scenarios.json",
    "challenge_v8_live": ROOT
    / "tests"
    / "action_policy"
    / "corpus"
    / "challenge_v8_live"
    / "scenarios.json",
}
DEFAULT_CORPUS = "challenge_v8_live"
FROZEN_POLICY_SHA_V5 = "0271c624e93e3f8e6f01d5f6dafcf03a377c8b8b"
FREEZE_MANIFEST_SHA_V5 = "639babcc13c69ee498bbe7a9700f7362a7586808"
FROZEN_POLICY_SHA_V7 = "61e17934f7be3b10ca5df9b2581cb0a8b853c1fe"
FREEZE_MANIFEST_SHA_V7 = "9948077298c66bba09f3ac1cf1c9ca349d22d7ec"
FROZEN_POLICY_SHA_V8 = "c0fa158bd2ffb4109d1f0776c3b3245cdff31ce4"
FREEZE_MANIFEST_SHA_V8 = "822c391bc7da1fe3aad57e261f962718cd633132"


def _load_cases(challenge_path: Path) -> list[dict[str, Any]]:
    return json.loads(challenge_path.read_text(encoding="utf-8"))


def _build_live_snapshot(live: dict[str, Any]) -> PolicySnapshot:
    """EngineState → build_policy_snapshot (required for v8 challenge parity)."""
    state = EngineState(
        call_id="challenge-live",
        turn_seq=int(live.get("turn_seq", 5)),
        first_user_turn_received=True,
    )
    if live.get("wellness_answered"):
        state.slots["wellness"] = SlotStatus.FILLED
        state.background_goal_status["wellness"] = "answered"
    for ep in live.get("episodes", ()) or ():
        state.issue_episodes[ep["episode_id"]] = IssueEpisode(
            episode_id=ep["episode_id"],
            primary_label=ep.get("primary_label", "issue"),
            kind=ep.get("kind", "symptom"),
            known_attributes=dict(ep.get("known", {})),
            status=ep.get("status", "open"),
        )
        # speaker_owned is derived from observations in live builder; force via observation skip
        # by leaving observations empty → default speaker_owned True. For other-person cases,
        # inject a non-speaker observation marker after build via from_mapping patch if needed.
    if live.get("active_episode_id"):
        state.active_episode_id = live["active_episode_id"]
    if live.get("pending_episode_ids") is not None:
        state.pending_episode_ids = list(live["pending_episode_ids"])
    if "pending_episode_attribute" in live:
        state.pending_episode_attribute = live["pending_episode_attribute"]
    if live.get("important_to_share_asked"):
        state.important_to_share_asked = True
    if live.get("important_to_share_resolved"):
        state.important_to_share_resolved = True
    if live.get("required_background_goals"):
        state.required_background_goals = set(live["required_background_goals"])
    dq = live.get("delivered_question")
    if dq:
        state.delivered_question = Question(
            question_id=dq["question_id"],
            intent=dq.get("intent", ""),
            slot=dq.get("slot", "wellness"),
            text=dq.get("text", ""),
        )
    snap = build_policy_snapshot(state)
    # Override speaker_owned for explicit other-person episodes.
    patched = []
    owned_map = {
        ep["episode_id"]: bool(ep.get("speaker_owned", True)) for ep in (live.get("episodes") or ())
    }
    for ep in snap.episodes:
        if ep.episode_id in owned_map and owned_map[ep.episode_id] != ep.speaker_owned:
            from dataclasses import replace

            patched.append(replace(ep, speaker_owned=owned_map[ep.episode_id]))
        else:
            patched.append(ep)
    if patched != list(snap.episodes):
        from dataclasses import replace as dc_replace

        snap = dc_replace(snap, episodes=tuple(patched))
    if live.get("user_burden") is not None:
        from dataclasses import replace as dc_replace

        snap = dc_replace(snap, user_burden=float(live["user_burden"]))
        if live.get("questions_asked_this_episode") is not None:
            snap = dc_replace(
                snap,
                questions_asked_this_episode=int(live["questions_asked_this_episode"]),
            )
    return snap


def _scored_row(item) -> dict[str, Any]:
    return {
        "action": item.action.key.label(),
        "score": item.score,
        "contributions": item.contributions,
        "features": item.features,
    }


def run_challenge(
    *,
    challenge_path: Path,
    frozen_policy_sha: str | None = None,
    freeze_manifest_commit: str | None = None,
) -> dict[str, Any]:
    cases = _load_cases(challenge_path)
    rows: list[dict[str, Any]] = []
    passed = 0
    failed = 0
    forbidden_count = 0
    constraint_violation_count = 0
    p0_like_failures = 0
    p0_like_total = 0

    for case in cases:
        if case.get("live_state") is not None:
            snapshot = _build_live_snapshot(case["live_state"])
            build_path = "engine_state"
        else:
            snapshot = PolicySnapshot.from_mapping(case["snapshot"])
            build_path = "from_mapping"
        ctx = TurnContextView.from_mapping(case.get("context", {}))
        acceptable = set(case.get("acceptable", ()))
        forbidden = set(case.get("forbidden", ()))
        is_p0_like = bool(case.get("p0_like")) or case["id"].startswith(
            (
                "ch_safety",
                "ch_no_ack",
                "ch_no_premature",
                "ch_no_repeat",
                "v6ch_no_",
                "v6ch_safety",
                "v7ch_no_",
                "v7ch_safety",
                "v8ch_no_",
                "v8ch_safety",
            )
        )

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
                "build_path": build_path,
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
        "frozen_policy_sha": frozen_policy_sha,
        "freeze_manifest_commit": freeze_manifest_commit,
        "challenge_corpus_commit": None,
        "policy_version": POLICY_VERSION,
        "corpus_path": str(challenge_path.relative_to(ROOT)),
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
        "--corpus",
        choices=sorted(CORPUS_CHOICES),
        default=DEFAULT_CORPUS,
        help="Challenge corpus split (default: v6 independent challenge)",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Report path (default depends on --corpus)",
    )
    parser.add_argument("--frozen-policy-sha", default="")
    parser.add_argument("--freeze-manifest-sha", default="")
    parser.add_argument("--challenge-sha", default="")
    args = parser.parse_args()

    challenge_path = CORPUS_CHOICES[args.corpus]
    default_outputs = {
        "challenge_frozen": "docs/evaluation/action-policy-phase1-v5-challenge.json",
        "challenge_v6_frozen": "docs/evaluation/action-policy-phase1-v6-challenge.json",
        "challenge_v7_frozen": "docs/evaluation/action-policy-phase1-v7-challenge.json",
        "challenge_v8_live": "docs/evaluation/action-policy-phase1-v8-challenge.json",
    }
    output = args.output or str(ROOT / default_outputs[args.corpus])
    frozen_defaults = {
        "challenge_frozen": FROZEN_POLICY_SHA_V5,
        "challenge_v7_frozen": FROZEN_POLICY_SHA_V7,
        "challenge_v8_live": FROZEN_POLICY_SHA_V8,
    }
    manifest_defaults = {
        "challenge_frozen": FREEZE_MANIFEST_SHA_V5,
        "challenge_v7_frozen": FREEZE_MANIFEST_SHA_V7,
        "challenge_v8_live": FREEZE_MANIFEST_SHA_V8,
    }
    frozen_sha = args.frozen_policy_sha or frozen_defaults.get(args.corpus, "")
    manifest_sha = args.freeze_manifest_sha or manifest_defaults.get(args.corpus, "")

    report = run_challenge(
        challenge_path=challenge_path,
        frozen_policy_sha=frozen_sha or None,
        freeze_manifest_commit=manifest_sha or None,
    )
    if args.challenge_sha:
        report["challenge_corpus_commit"] = args.challenge_sha
    out = Path(output)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "passed_gate": report["passed_gate"],
                "passed": report["passed"],
                "failed": report["failed"],
                "forbidden_count": report["forbidden_count"],
                "constraint_violation_count": report["constraint_violation_count"],
                "pass_rate": report["pass_rate"],
                "frozen_policy_sha": report["frozen_policy_sha"],
                "freeze_manifest_commit": report["freeze_manifest_commit"],
                "challenge_corpus_commit": report["challenge_corpus_commit"],
                "output": str(out.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["passed_gate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
