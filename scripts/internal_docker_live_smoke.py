#!/usr/bin/env python3
"""Phase A — one full daily-check inside docker-compose (diagnostic only).

Status on success: INTERNAL_DOCKER_LIVE_SMOKE = PASS
Does NOT imply TELEPHONY ACCEPTED (external Mac/LAN path untested).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("IMVERA_INTERNAL_DOCKER_SMOKE", "1")
os.environ.setdefault("IMVERA_BLACKBOX_SIP_BACKEND", "pyvoip")

from tools.blackbox_caller.import_guard import assert_blackbox_clean
from tools.voice_lab.live_debug_runner import run_live_debug


def main() -> int:
    assert_blackbox_clean(context="internal_docker_live_smoke")
    calls = int(os.environ.get("IMVERA_INTERNAL_DOCKER_CALLS", "1"))
    scenario = os.environ.get("IMVERA_LIVE_DEBUG_SCENARIO", "good-clean_short-00")
    stop_on_fail = os.environ.get("IMVERA_LIVE_DEBUG_STOP_ON_FAIL", "1") == "1"

    print(
        f"internal-docker-live-smoke: calls={calls} scenario={scenario} "
        f"backend={os.environ.get('IMVERA_BLACKBOX_SIP_BACKEND', 'pyvoip')}",
        flush=True,
    )
    try:
        summary = run_live_debug(
            call_count=calls,
            profile="full",
            scenario_id=scenario if calls == 1 else None,
            stop_on_fail=stop_on_fail,
        )
    except Exception as exc:
        print(f"INTERNAL_DOCKER_LIVE_SMOKE = FAIL ({exc})", file=sys.stderr)
        return 1

    if summary.passed and summary.calls_passed == summary.calls_attempted:
        print(
            f"INTERNAL_DOCKER_LIVE_SMOKE = PASS "
            f"({summary.calls_passed}/{summary.calls_attempted} run_id={summary.run_id})",
            flush=True,
        )
        print("NOTE: internal docker smoke only — not external telephony acceptance.", flush=True)
        return 0

    print(
        f"INTERNAL_DOCKER_LIVE_SMOKE = FAIL "
        f"({summary.calls_passed}/{summary.calls_attempted} run_id={summary.run_id})",
        file=sys.stderr,
    )
    for fail in summary.failures[:3]:
        print(f"  {fail.get('scenario_id')}: {fail.get('errors')}", file=sys.stderr)
    print(f"  debug: .run/live_debug/{summary.run_id}/call-*/DEBUG_REPORT.md", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
