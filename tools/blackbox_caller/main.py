#!/usr/bin/env python3
"""Black-box live SIP/RTP E2E gate CLI."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.blackbox_caller.import_guard import assert_blackbox_clean
from tools.blackbox_caller.runner import run_live_soak
from tools.blackbox_caller.scenarios.catalog import catalog_size, write_catalog_json


def main() -> int:
    parser = argparse.ArgumentParser(description="IMVERA black-box live SIP E2E gate")
    parser.add_argument(
        "--calls",
        type=int,
        default=int(os.environ.get("IMVERA_LIVE_CALLS", "1")),
        help="Number of consecutive calls (default 1)",
    )
    parser.add_argument(
        "--write-catalog",
        action="store_true",
        help="Write deterministic scenario catalog JSON and exit",
    )
    parser.add_argument("--run-id", default=os.environ.get("IMVERA_LIVE_RUN_ID"))
    args = parser.parse_args()

    assert_blackbox_clean(context="main")

    if args.write_catalog:
        out = ROOT / "tools" / "blackbox_caller" / "scenarios" / "catalog.json"
        n = write_catalog_json(out)
        print(f"wrote {n} scenarios to {out}")
        return 0

    print(f"blackbox gate: {args.calls} call(s), catalog={catalog_size()}")
    try:
        summary = run_live_soak(call_count=args.calls, run_id=args.run_id)
    except Exception as exc:
        print(f"BLACKBOX_GATE=FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        f"LIVE E2E: {summary.calls_passed}/{summary.calls_attempted} passed "
        f"run_id={summary.run_id} overall={'PASS' if summary.passed else 'FAIL'}"
    )
    if not summary.passed:
        for fail in summary.failures[:5]:
            print(f"  FAIL {fail['scenario_id']}: {fail['errors']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
