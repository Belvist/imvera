"""Parallel corpus runner with category report.

NOT live SIP/PSTN. Proves Session/Planner dialogue correctness at scale.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Ensure repo root on path when invoked as script
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.corpus.execute import run_scenario  # noqa: E402
from tests.corpus.generate import (  # noqa: E402
    CORPUS_SEED,
    generate_scenarios,
    scenario_count_by_category,
)
from tests.corpus.invariants import check_status_invariants  # noqa: E402
from tests.corpus.models import Scenario, ScenarioResult  # noqa: E402


def _run_one(scenario: Scenario) -> ScenarioResult:
    return run_scenario(scenario)


def run_corpus(
    *,
    workers: int = 1,
    minimum: int = 1000,
    seed: int = CORPUS_SEED,
    fail_fast: bool = False,
) -> tuple[list[ScenarioResult], float]:
    scenarios = generate_scenarios(seed=seed, minimum=minimum)
    t0 = time.perf_counter()
    results: list[ScenarioResult] = []

    if workers <= 1:
        for scenario in scenarios:
            result = run_scenario(scenario)
            results.append(result)
            if fail_fast and not result.ok:
                break
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run_one, s): s.id for s in scenarios}
            for fut in as_completed(futures):
                result = fut.result()
                results.append(result)
                if fail_fast and not result.ok:
                    for pending in futures:
                        pending.cancel()
                    break

    wall = time.perf_counter() - t0
    # Stable order by scenario id
    results.sort(key=lambda r: r.scenario_id)
    return results, wall


def format_report(
    results: list[ScenarioResult],
    wall_s: float,
    *,
    seed: int,
) -> str:
    total = len(results)
    passed = sum(1 for r in results if r.ok)
    failed = total - passed
    by_cat = Counter(r.category for r in results)
    fail_by_cat: dict[str, int] = defaultdict(int)
    for r in results:
        if not r.ok:
            fail_by_cat[r.category] += 1
    throughput = total / wall_s if wall_s > 0 else 0.0

    lines = [
        "=== Dialogue corpus report ===",
        "LAYER: CallSession + rule interpreter + StatusEngine invariants",
        "NOT VERIFIED here: live SIP × N, real STT/TTS/LLM, Zoiper audio",
        f"seed={seed}",
        f"total={total} passed={passed} failed={failed} "
        f"pass_rate={passed / total * 100:.2f}%" if total else "total=0",
        f"wall_s={wall_s:.3f} throughput={throughput:.1f} scenarios/sec",
        "",
        "by_category:",
    ]
    for cat, count in sorted(by_cat.items()):
        fails = fail_by_cat.get(cat, 0)
        lines.append(f"  {cat}: {count} (failed={fails})")

    if failed:
        lines.append("")
        lines.append("failures (up to 20):")
        shown = 0
        for r in results:
            if r.ok:
                continue
            lines.append(f"  [{r.category}] {r.scenario_id}: {r.errors[0]}")
            shown += 1
            if shown >= 20:
                break
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--minimum", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=CORPUS_SEED)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--list-categories", action="store_true")
    args = parser.parse_args(argv)

    if args.list_categories:
        cats = scenario_count_by_category(
            generate_scenarios(seed=args.seed, minimum=args.minimum)
        )
        print(json.dumps(cats, ensure_ascii=False, indent=2))
        print(f"total={sum(cats.values())}")
        return 0

    status_errors = check_status_invariants()
    if status_errors:
        print("HARD STATUS INVARIANT FAILURES:")
        for err in status_errors:
            print(f"  {err}")
        return 1

    results, wall = run_corpus(
        workers=max(1, args.workers),
        minimum=args.minimum,
        seed=args.seed,
        fail_fast=args.fail_fast,
    )
    report = format_report(results, wall, seed=args.seed)
    print(report)

    if args.json_out:
        payload = {
            "seed": args.seed,
            "wall_s": wall,
            "total": len(results),
            "passed": sum(1 for r in results if r.ok),
            "failed": sum(1 for r in results if not r.ok),
            "results": [
                {
                    "id": r.scenario_id,
                    "category": r.category,
                    "ok": r.ok,
                    "errors": r.errors,
                    "elapsed_ms": r.elapsed_ms,
                }
                for r in results
            ],
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"json_out={args.json_out}")

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
