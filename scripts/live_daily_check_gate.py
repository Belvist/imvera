#!/usr/bin/env python3
"""Live SIP daily-check debug gate — real calls, greeting → goodbye, full trace bundle."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.blackbox_caller.import_guard import assert_blackbox_clean
from tools.voice_lab.live_debug_runner import run_live_debug


def main() -> int:
    parser = argparse.ArgumentParser(
        description="IMVERA live SIP full daily-check debug gate (real RTP, server trace primary)"
    )
    parser.add_argument(
        "--calls",
        type=int,
        default=int(os.environ.get("IMVERA_LIVE_DEBUG_CALLS", "1")),
        help="Number of scenarios (default 1; use 100 for ADR-014 soak)",
    )
    parser.add_argument(
        "--profile",
        choices=["full", "all"],
        default=os.environ.get("IMVERA_LIVE_DEBUG_PROFILE", "full"),
        help="full = families with goodbye path; all = first N catalog scenarios",
    )
    parser.add_argument(
        "--scenario",
        default=os.environ.get("IMVERA_LIVE_DEBUG_SCENARIO", ""),
        help="Run one scenario by id (e.g. good-clean_short-00)",
    )
    parser.add_argument("--run-id", default=os.environ.get("IMVERA_LIVE_DEBUG_RUN_ID", ""))
    parser.add_argument(
        "--stop-on-fail",
        action="store_true",
        default=os.environ.get("IMVERA_LIVE_DEBUG_STOP_ON_FAIL", "1") == "1",
    )
    args = parser.parse_args()

    assert_blackbox_clean(context="live_daily_check_gate")
    print(
        f"live-daily-check-gate: calls={args.calls} profile={args.profile} "
        f"scenario={args.scenario or '(catalog)'}",
        flush=True,
    )
    try:
        summary = run_live_debug(
            call_count=args.calls,
            run_id=args.run_id or None,
            profile=args.profile,
            scenario_id=args.scenario or None,
            stop_on_fail=args.stop_on_fail,
        )
    except Exception as exc:
        print(f"LIVE_DAILY_CHECK=FAIL: {exc}", file=sys.stderr)
        return 1

    print(
        f"LIVE_DAILY_CHECK: {summary.calls_passed}/{summary.calls_attempted} passed "
        f"run_id={summary.run_id} overall={'PASS' if summary.passed else 'FAIL'}",
        flush=True,
    )
    if not summary.passed:
        for fail in summary.failures[:5]:
            print(
                f"  FAIL call-{fail.get('call_index')} {fail.get('scenario_id')}: "
                f"{fail.get('errors')}",
                file=sys.stderr,
            )
        print(f"  debug: .run/live_debug/{summary.run_id}/call-*/DEBUG_REPORT.md", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
