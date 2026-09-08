#!/usr/bin/env python3
"""DialogueEngine corpus gate — >=500 full daily-check scenarios, 500/500 required."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from packages.dialogue_engine.corpus.generator import (
    CORPUS_VERSION,
    count_by_category,
    generate_corpus,
)
from packages.dialogue_engine.corpus.report import aggregate_results
from packages.dialogue_engine.corpus.runner import CorpusRunner


def main() -> int:
    t0 = time.monotonic()
    corpus = generate_corpus()
    results = [CorpusRunner(sc).run() for sc in corpus]
    elapsed = time.monotonic() - t0

    report = aggregate_results(
        results,
        corpus_version=CORPUS_VERSION,
        category_totals=count_by_category(corpus),
        elapsed_s=elapsed,
    )
    out_path = ROOT / ".run" / "dialogue_corpus_report.json"
    report.write(out_path)

    print(f"dialogue-corpus-gate: {report.passed}/{report.total} PASS ({elapsed:.2f}s)")
    print(f"  by_wellness: {report.by_wellness}")
    print(f"  report: {out_path}")
    if report.failures:
        print("  failures (first 10):")
        for line in report.failures[:10]:
            print(f"    - {line}")

    return 0 if report.gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
