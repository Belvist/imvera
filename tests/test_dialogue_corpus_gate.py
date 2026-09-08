"""Production DialogueEngine corpus gate — >=500 full daily-check trajectories."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from packages.dialogue_engine.corpus.generator import (
    CORPUS_VERSION,
    SCENARIOS_PER_CATEGORY,
    WELLNESS_CATEGORIES,
    count_by_category,
    generate_corpus,
)
from packages.dialogue_engine.corpus.runner import CorpusRunner

pytestmark = pytest.mark.dialogue_engine

def _corpus():
    return generate_corpus()


def test_corpus_size_and_categories() -> None:
    CORPUS = _corpus()
    assert len(CORPUS) == 500
    counts = count_by_category(CORPUS)
    assert counts == {c: SCENARIOS_PER_CATEGORY for c in WELLNESS_CATEGORIES}


def test_corpus_all_scenarios_pass() -> None:
    CORPUS = _corpus()
    failures: list[str] = []
    t0 = time.monotonic()
    for scenario in CORPUS:
        result = CorpusRunner(scenario).run()
        if not result.passed:
            failures.append(f"{scenario.id}: {'; '.join(result.errors)}")
    elapsed = time.monotonic() - t0
    assert not failures, (
        f"{len(failures)}/500 failed in {elapsed:.2f}s\n" + "\n".join(failures[:15])
    )


@pytest.mark.parametrize("category", list(WELLNESS_CATEGORIES))
def test_corpus_category_sample(category: str) -> None:
    CORPUS = _corpus()
    sample = next(sc for sc in CORPUS if sc.wellness_category == category)
    result = CorpusRunner(sample).run()
    assert result.passed, result.errors


def test_corpus_report_schema(tmp_path: Path) -> None:
    from packages.dialogue_engine.corpus.report import aggregate_results

    CORPUS = _corpus()
    results = [CorpusRunner(CORPUS[0]).run()]
    report = aggregate_results(
        results,
        corpus_version=CORPUS_VERSION,
        category_totals=count_by_category(CORPUS),
        elapsed_s=0.01,
    )
    out = tmp_path / "report.json"
    report.write(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "total" in data
    assert "by_wellness" in data
    assert data["gate"] in ("PASS", "FAIL")
