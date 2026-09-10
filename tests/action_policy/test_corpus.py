from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView

CORPUS = Path(__file__).parent / "corpus"


def _cases(split: str):
    out = []
    for path in sorted((CORPUS / split).glob("*.json")):
        out.extend(json.loads(path.read_text(encoding="utf-8")))
    return out


@pytest.mark.parametrize("split", ["development", "held_out", "p0_golden"])
def test_corpus_actions_are_acceptable_and_not_forbidden(split: str) -> None:
    cases = _cases(split)
    assert cases, f"missing {split} corpus"
    failures = []
    for case in cases:
        snapshot = PolicySnapshot.from_mapping(case["snapshot"])
        ctx = TurnContextView.from_mapping(case.get("context", {}))
        decision = choose(snapshot, ctx)
        key = decision.chosen.key.label()
        if key not in case["acceptable"] or key in case.get("forbidden", []):
            failures.append({
                "id": case["id"],
                "chosen": key,
                "acceptable": case["acceptable"],
                "forbidden": case.get("forbidden", []),
            })
    assert not failures, failures


def test_p0_golden_is_nontrivial_and_strict() -> None:
    cases = _cases("p0_golden")
    assert len(cases) >= 10
    for case in cases:
        assert case["acceptable"]
        assert case.get("forbidden")
        assert case.get("source")


def test_held_out_threshold_is_at_least_95_percent() -> None:
    cases = _cases("held_out")
    passed = 0
    forbidden = 0
    for case in cases:
        decision = choose(
            PolicySnapshot.from_mapping(case["snapshot"]),
            TurnContextView.from_mapping(case.get("context", {})),
        )
        key = decision.chosen.key.label()
        passed += int(key in case["acceptable"] and key not in case.get("forbidden", []))
        forbidden += int(key in case.get("forbidden", []))
    assert forbidden == 0
    assert passed / len(cases) >= 0.95
