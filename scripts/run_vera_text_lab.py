#!/usr/bin/env python3
"""Interactive text lab for Vera Golden Path (Stage A)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from golden_path import GoldenPathEngine, status_line
from golden_path.generation_profile import VERA_DIALOGUE_GENERATION_PROFILE
from golden_path.llm import GoldenPathLLM, LLMHealthStatus, LLMRuntimeError, MockLLM


def _print_owner_banner(engine: GoldenPathEngine, health: LLMHealthStatus | None) -> None:
    print("VERA GOLDEN PATH")
    if health is not None:
        raw = health.raw
        print(f"MODEL={health.model_id}")
        print(f"THINKING={raw.get('thinking', False)}")
        print(f"PROFILE={raw.get('generation_profile', VERA_DIALOGUE_GENERATION_PROFILE)}")
        print(f"LLM_READY={health.ready}")
    else:
        print("MODEL=mock")
        print("THINKING=n/a")
        print("PROFILE=mock")
        print("LLM_READY=true")
    print("LEGACY=OFF")
    print(status_line())
    print(f"TRACE={engine.trace_path}")
    print("")


def _print_bad_turns_report(trace_path: str) -> None:
    path = Path(trace_path)
    if not path.is_file():
        return
    marks: set[int] = set()
    turns: dict[int, dict[str, object]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("event") == "owner_mark":
            marks.add(int(rec["payload"]["turn_no"]))
        if "turn_no" in rec and "user_text" in rec:
            turns[int(rec["turn_no"])] = rec

    if not marks:
        print("\n--- Owner BAD turns: none marked ---")
        return

    print("\n========== OWNER BAD TURNS REPORT ==========")
    for turn_no in sorted(marks):
        rec = turns.get(turn_no)
        if not rec:
            print(f"\nTURN {turn_no}: (trace record missing)")
            continue
        print(f"\nTURN {turn_no}")
        print(f"USER: {rec.get('user_text')}")
        print(f"FINAL VERA: {rec.get('final_text')}")
        analysis = rec.get("analysis") or {}
        print(f"ANALYZER: {analysis.get('kind')}")
        planner = rec.get("planner_action") or {}
        print(f"PLANNER: {planner.get('action_name') or planner.get('action')}")
        print(f"CONTENT PLAN: {json.dumps(rec.get('content_plan'), ensure_ascii=False)}")
        print(f"RAW QWEN: {rec.get('raw_llm_output')}")
        validator = rec.get("validator_result") or rec.get("validator") or {}
        print(f"VALIDATOR: {validator}")
        print(
            f"REGEN/FALLBACK: regen={rec.get('regen_used')} "
            f"fallback={rec.get('fallback_used')} "
            f"deterministic={rec.get('deterministic')}"
        )
        print("ROOT CAUSE: (owner verdict pending — not auto-assigned)")
    print("\n============================================\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Vera Golden Path text REPL")
    parser.add_argument("--trace-dir", default="", help="JSONL trace directory")
    parser.add_argument("--llm-url", default="", help="Override MOSS_LLM_URL")
    parser.add_argument("--session-id", default="", help="Fixed session id")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use MockLLM (CI/offline); default is real LLM on MOSS_LLM_URL",
    )
    args = parser.parse_args()

    if args.llm_url:
        import os
        os.environ["MOSS_LLM_URL"] = args.llm_url

    health: LLMHealthStatus | None = None
    if args.mock:
        llm = MockLLM()
    else:
        llm = GoldenPathLLM(base_url=args.llm_url or None)
        try:
            health = llm.require_ready()
        except LLMRuntimeError as exc:
            print(exc.code, file=sys.stderr)
            if exc.detail:
                print(exc.detail, file=sys.stderr)
            return 1

    engine = GoldenPathEngine(
        llm=llm,
        trace_dir=args.trace_dir or None,
        session_id=args.session_id or None,
    )
    greeting = engine.begin_session()
    _print_owner_banner(engine, health)
    print("Vera Golden Path text lab — /help for commands")
    print(f"\nВера: {greeting}\n")

    while True:
        try:
            line = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n/session end")
            _print_bad_turns_report(engine.trace_path)
            engine.end_session()
            return 0

        if not line:
            continue

        cmd = line.lower()
        if cmd in ("/quit", "/q"):
            _print_bad_turns_report(engine.trace_path)
            engine.end_session()
            print(status_line())
            return 0
        if cmd == "/reset":
            greeting = engine.reset()
            print(f"session reset → {engine.session_id}")
            print(f"Вера: {greeting}\n")
            continue
        if cmd == "/trace":
            print(engine.trace_path)
            continue
        if cmd == "/status":
            print(status_line())
            print(engine.state.compact_json())
            continue
        if cmd == "/mark":
            if engine.mark_last_turn():
                print(f"[marked turn {engine.turn_no} as BAD]")
            else:
                print("[no turn to mark]")
            continue
        if cmd == "/help":
            print("Commands: /reset /trace /status /mark /quit")
            print("LLM errors print as TURN_FAILED_* codes (no fake conversational reply).")
            continue

        try:
            result = engine.handle_turn(line)
        except RuntimeError as exc:
            if "session already ended" in str(exc).lower():
                print("\n(сессия завершена — введите /new для нового разговора)\n")
                continue
            raise
        except LLMRuntimeError as exc:
            print(f"\n*** {exc.code} ***", file=sys.stderr)
            if exc.detail:
                print(exc.detail, file=sys.stderr)
            print("(no assistant reply — fix LLM and retry)\n", file=sys.stderr)
            continue

        fb = " fallback" if result.fallback_used else ""
        reg = " regen" if result.regen_used else ""
        det = " deterministic" if result.deterministic else ""
        print(f"\nВера: {result.assistant_text}")
        print(
            f"[plan={result.plan.action_name()} turn={result.turn_no}"
            f"{fb}{reg}{det}]\n"
        )


if __name__ == "__main__":
    raise SystemExit(main())
