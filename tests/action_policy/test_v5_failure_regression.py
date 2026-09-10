from __future__ import annotations

import json
from pathlib import Path

from packages.dialogue_engine.action_policy.actions import ActionKind
from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.snapshot import PolicySnapshot, TurnContextView

CORPUS = Path(__file__).parent / "corpus" / "development" / "scenarios.json"


def _case(case_id: str) -> dict:
    for item in json.loads(CORPUS.read_text(encoding="utf-8")):
        if item["id"] == case_id:
            return item
    raise KeyError(case_id)


def test_v5_challenge_failure_severity_then_current() -> None:
    case = _case("dev_v5_fail_severity_then_current")
    decision = choose(
        PolicySnapshot.from_mapping(case["snapshot"]),
        TurnContextView.from_mapping(case["context"]),
    )
    key = decision.chosen.key.label()
    assert key in case["acceptable"]
    assert key not in case["forbidden"]
    assert decision.chosen.kind == ActionKind.ASK_EPISODE


def test_v5_challenge_failure_pending_functional_impact() -> None:
    case = _case("dev_v5_fail_pending_functional_impact")
    decision = choose(
        PolicySnapshot.from_mapping(case["snapshot"]),
        TurnContextView.from_mapping(case["context"]),
    )
    key = decision.chosen.key.label()
    assert key in case["acceptable"]
    assert key not in case["forbidden"]
    assert decision.chosen.kind != ActionKind.IMPORTANT_TO_SHARE
