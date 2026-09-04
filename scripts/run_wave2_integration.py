#!/usr/bin/env python3
"""Wave 2 real LLM integration — 10-turn scenario via canonical :9500 gateway."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from golden_path.engine import GoldenPathEngine
from golden_path.llm import GoldenPathLLM
from golden_path.spoken_quality import check_spoken_quality

WAVE2_TURNS: tuple[str, ...] = (
    "нормально",
    "настроение хорошее",
    "спал хорошо",
    "а зачем вы звоните?",
    "да ничего не планирую",
    "не хочу про настроение",
    "секундочку",
    "что вы спросили?",
    "нет, не голова, спина",
    "я устал уже отвечать",
)

EXPECTED_ACTIONS: dict[int, str] = {
    1: "ASK_SLOT(mood)",
    2: "ASK_SLOT(sleep)",
    3: "ASK_SLOT(plans)",
    4: "ANSWER_USER(WHY_CALLING)",
    5: "CLOSE",
    6: "HANDLE_REFUSAL",
    7: "WAIT",
    8: "REPAIR",
    9: "HANDLE_CORRECTION",
    10: "HANDLE_FATIGUE",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Wave 2 real LLM integration test")
    parser.add_argument("--trace-dir", default="golden_path/traces")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on action mismatch")
    args = parser.parse_args()

    llm = GoldenPathLLM()
    health = llm.check_health()
    if not health.ready:
        print("LLM not ready on canonical gateway — start scripts/run_llm_host.sh", file=sys.stderr)
        print(json.dumps(health.to_dict(), ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    engine = GoldenPathEngine(llm=llm, trace_dir=args.trace_dir, session_id="wave2-integration")
    greeting = engine.begin_session()
    print(f"GREETING: {greeting}\n")

    failures: list[str] = []
    spoken_failures: list[str] = []
    records: list[dict[str, object]] = []

    for idx, user_text in enumerate(WAVE2_TURNS, start=1):
        result = engine.handle_turn(user_text)
        action_name = result.plan.action_name()
        expected = EXPECTED_ACTIONS.get(idx)
        ok = expected is None or action_name == expected
        if not ok:
            failures.append(f"turn {idx}: expected {expected}, got {action_name}")

        spoken_v = check_spoken_quality(result.assistant_text)
        spoken_ok = not spoken_v
        if not spoken_ok:
            spoken_failures.append(
                f"turn {idx}: spoken violations {spoken_v}: {result.assistant_text!r}"
            )

        record = {
            "turn": idx,
            "user": user_text,
            "analysis": result.analysis.to_dict(),
            "state_after_user": engine.state.compact_dict(),
            "planner_action": result.plan.to_dict(),
            "content_plan": result.content_plan,
            "raw_llm_output": result.raw_llm_output,
            "validator_result": result.validator_result,
            "regen_used": result.regen_used,
            "fallback_used": result.fallback_used,
            "deterministic": result.deterministic,
            "final_text": result.assistant_text,
            "spoken_ok": spoken_ok,
            "spoken_violations": spoken_v,
            "action_ok": ok,
        }
        records.append(record)
        status = "OK" if ok and spoken_ok else "FAIL"
        print(f"TURN {idx}")
        print(f"USER: {user_text}")
        print(f"FINAL VERA: {result.assistant_text}")
        print(f"  action: {action_name} [{'OK' if ok else 'MISMATCH'}]")
        if spoken_v:
            print(f"  spoken: FAIL {spoken_v}")
        print(f"  regen={result.regen_used} fallback={result.fallback_used} det={result.deterministic}")
        print()

    out_path = Path(args.trace_dir) / "wave2-integration-summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "session_id": engine.session_id,
                "trace_path": engine.trace_path,
                "llm": health.to_dict(),
                "failures": failures,
                "spoken_failures": spoken_failures,
                "records": records,
                "planner_actions_ok": len(failures) == 0,
                "spoken_quality_ok": len(spoken_failures) == 0,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Summary: {out_path}")
    print(f"Trace: {engine.trace_path}")

    if failures:
        print(f"\n{len(failures)} action mismatch(es):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
    if spoken_failures:
        print(f"\n{len(spoken_failures)} spoken quality failure(s):", file=sys.stderr)
        for f in spoken_failures:
            print(f"  - {f}", file=sys.stderr)
    if args.strict and (failures or spoken_failures):
        return 1
    if failures:
        return 1
    print("\nWAVE_2_INTEGRATION: PASS (10/10 planner actions)")
    if spoken_failures:
        print("SPOKEN_QUALITY: FAIL", file=sys.stderr)
        return 1
    print("SPOKEN_QUALITY: PASS (10/10 FINAL outputs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
