#!/usr/bin/env python3
"""Run Golden Path scenario pack with semantic assertions."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from golden_path.engine import GoldenPathEngine
from golden_path.llm import MockLLM
from golden_path.planner import PlannerAction
from golden_path.slots import SlotName, SlotStatus
from golden_path.status import status_line


SCENARIOS_DIR = _REPO / "golden_path" / "scenarios"


def _load_scenarios() -> list[dict[str, Any]]:
    files = sorted(SCENARIOS_DIR.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no scenarios in {SCENARIOS_DIR}")
    out: list[dict[str, Any]] = []
    for path in files:
        with path.open(encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


def _slot_status(state, slot: str) -> str:
    name = SlotName(slot)
    return state.slot_statuses.get(name, SlotStatus.OPEN).value


def _check_assertion(engine: GoldenPathEngine, history: list[dict[str, Any]], spec: dict[str, Any]) -> str | None:
    atype = spec["type"]
    state = engine.state

    if atype == "min_turns":
        required = int(spec.get("count", 8))
        if len(history) < required:
            return (
                f"scenario processed {len(history)} user turns; "
                f"expected at least {required}"
            )
        return None

    if atype == "slot_status":
        slot = spec["slot"]
        expected = spec["status"]
        actual = _slot_status(state, slot)
        if actual != expected:
            return f"slot {slot}: expected {expected}, got {actual}"
        return None

    if atype == "fact_equals":
        key = spec["key"]
        expected = spec["value"]
        actual = state.facts.get(key)
        if actual != expected:
            return f"fact {key}: expected {expected}, got {actual}"
        return None

    if atype == "never_plan":
        slot = spec.get("slot")
        action = spec.get("action", "")
        prev_slots: dict[str, str] = {}
        for item in history:
            plan_name = item["plan"]
            if action and plan_name == action:
                return f"forbidden plan {action} at turn {item['turn']}"
            if slot and plan_name == f"ASK_SLOT({slot})":
                if prev_slots.get(slot) in ("ANSWERED", "DECLINED"):
                    return f"re-asked {slot} while {prev_slots[slot]} at turn {item['turn']}"
            prev_slots = item.get("slots", prev_slots)
        return None

    if atype == "user_question_before_slot":
        for item in history:
            if item["analysis"] == "DIRECT_USER_QUESTION":
                if not item["plan"].startswith("ANSWER_USER"):
                    return f"turn {item['turn']}: user question but plan={item['plan']}"
        return None

    if atype == "plan_on_turn":
        turn = int(spec["turn"])
        expected = spec["action"]
        for item in history:
            if item["turn"] == turn:
                if item["plan"] != expected:
                    return f"turn {turn}: expected {expected}, got {item['plan']}"
                return None
        return f"turn {turn}: expected {expected}, but turn was not processed"

    if atype == "analysis_on_turn":
        turn = int(spec["turn"])
        expected = spec["kind"]
        for item in history:
            if item["turn"] == turn:
                if item["analysis"] != expected:
                    return f"turn {turn}: expected analysis {expected}, got {item['analysis']}"
                return None
        return f"turn {turn}: expected analysis {expected}, but turn was not processed"

    if atype == "question_budget":
        violations = 0
        since = 0
        for item in history:
            text = item.get("assistant", "")
            if "?" in text:
                if since < 2 and item["turn"] > 1:
                    violations += 1
                since = 0
            else:
                since += 1
        if violations > int(spec.get("max_violations", 0)):
            return f"question budget violations={violations}"
        return None

    return f"unknown assertion type: {atype}"


def run_scenario(scenario: dict[str, Any], use_mock: bool) -> tuple[bool, list[str]]:
    from golden_path.llm import GoldenPathLLM

    llm: GoldenPathLLM | MockLLM = MockLLM() if use_mock else GoldenPathLLM()
    engine = GoldenPathEngine(llm=llm, session_id=f"scn-{scenario['id']}")
    engine.begin_session()

    history: list[dict[str, Any]] = []
    errors: list[str] = []

    for idx, user_text in enumerate(scenario.get("turns", []), start=1):
        analysis, pre_plan = engine.plan_only(user_text)

        try:
            result = engine.handle_turn(user_text)
        except Exception as exc:  # scenario failure; keep the pack running
            errors.append(
                f"{scenario['id']}: turn {idx} raised "
                f"{type(exc).__name__}: {exc}"
            )
            break

        if scenario.get("check_plans_before_handle") \
                and pre_plan.action_name() != result.plan.action_name():
            errors.append(
                f"{scenario['id']}: turn {idx} plan_only="
                f"{pre_plan.action_name()}, handle={result.plan.action_name()}"
            )

        history.append(
            {
                "turn": idx,
                "plan": result.plan.action_name(),
                "pre_plan": pre_plan.action_name(),
                "analysis": result.analysis.kind.value,
                "assistant": result.assistant_text,
                "slots": {
                    s.value: engine.state.slot_statuses[s].value
                    for s in SlotName
                },
            }
        )
        # Scripted fixtures often include padding turns after a goodbye.  A
        # real session cannot accept another user turn, so stop at the same
        # lifecycle boundary instead of crashing with "session already ended".
        if engine.ended:
            break

    for spec in scenario.get("assertions", []):
        err = _check_assertion(engine, history, spec)
        if err:
            errors.append(f"{scenario['id']}: {err}")

    engine.end_session()
    return len(errors) == 0, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any failure")
    parser.add_argument(
        "--live-llm",
        action="store_true",
        help="Use real MOSS_LLM_URL (slow; automated gate uses MockLLM)",
    )
    parser.add_argument("--scenario", default="", help="Run single scenario id")
    args = parser.parse_args()

    use_mock = not args.live_llm

    scenarios = _load_scenarios()
    if args.scenario:
        scenarios = [s for s in scenarios if s["id"] == args.scenario]
        if not scenarios:
            print(f"scenario not found: {args.scenario}", file=sys.stderr)
            return 2

    passed = 0
    failed = 0
    all_errors: list[str] = []

    print(status_line(), flush=True)
    print(f"running {len(scenarios)} scenarios (mock_llm={use_mock})", flush=True)

    for scenario in scenarios:
        ok, errors = run_scenario(scenario, use_mock=use_mock)
        if ok:
            passed += 1
            print(f"  PASS  {scenario['id']}", flush=True)
        else:
            failed += 1
            print(f"  FAIL  {scenario['id']}", flush=True)
            all_errors.extend(errors)

    print(f"\nautomated: {'PASS' if failed == 0 else 'FAIL'} ({passed}/{len(scenarios)})", flush=True)
    print("owner: WAITING", flush=True)
    print(status_line(), flush=True)

    if all_errors:
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)

    if args.strict and failed > 0:
        return 1
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
