#!/usr/bin/env python3
"""Golden Path Stage A — local LLM readiness gate (20 consecutive real calls)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from golden_path.llm import GoldenPathLLM, LLMRuntimeError, run_readiness_probe


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify local LLM readiness for Golden Path")
    parser.add_argument("--llm-url", default="", help="Override MOSS_LLM_URL")
    parser.add_argument("--calls", type=int, default=20, help="Consecutive probe calls")
    parser.add_argument("--json", action="store_true", help="Emit JSON report only")
    args = parser.parse_args()

    if args.llm_url:
        import os
        os.environ["MOSS_LLM_URL"] = args.llm_url

    llm = GoldenPathLLM(base_url=args.llm_url or None)
    try:
        report = run_readiness_probe(llm, calls=args.calls)
    except LLMRuntimeError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": exc.code, "detail": exc.detail}))
        else:
            print(exc.code, file=sys.stderr)
            if exc.detail:
                print(exc.detail, file=sys.stderr)
        return 1

    report["ok"] = True
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print("LLM_READINESS_OK")
    print(f"model_id={report['model_id']}")
    print(f"backend={report['backend']}")
    print(f"protocol={report['protocol']}")
    print(f"device={report['device']}")
    print(f"calls={report['calls']}")
    print(f"p50_ms={report['p50_ms']}")
    print(f"p95_ms={report['p95_ms']}")
    print(f"max_ms={report['max_ms']}")
    print(f"stage_a_latency_ok={report.get('stage_a_latency_ok')}")
    if report.get("ttft_p50_ms") is not None:
        print(f"ttft_p50_ms={report['ttft_p50_ms']}")
    if report.get("tokens_per_sec_avg") is not None:
        print(f"tokens_per_sec_avg={report['tokens_per_sec_avg']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
