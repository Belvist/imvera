"""Wellness matrix — delegates to production 500-scenario corpus gate."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.corpus.generator import (
    SCENARIOS_PER_CATEGORY,
    WELLNESS_CATEGORIES,
    count_by_category,
    generate_corpus,
)
from packages.dialogue_engine.corpus.runner import CorpusRunner
from tests.corpus.wellness_matrix import (
    generate_wellness_matrix,
    matrix_count_by_bucket,
)

pytestmark = pytest.mark.dialogue_engine


def test_wellness_matrix_counts() -> None:
    scenarios = generate_corpus()
    counts = count_by_category(scenarios)
    assert counts == {c: SCENARIOS_PER_CATEGORY for c in WELLNESS_CATEGORIES}
    assert len(scenarios) == 500


def test_wellness_matrix_clean_short_flat() -> None:
    flat = generate_wellness_matrix()
    assert len(flat) == len(WELLNESS_CATEGORIES) * 5  # 5 variants per category
    counts = matrix_count_by_bucket(flat)
    assert counts == {c: 5 for c in WELLNESS_CATEGORIES}


@pytest.mark.parametrize("category", list(WELLNESS_CATEGORIES))
def test_wellness_matrix_category_sample(category: str) -> None:
    scenario = next(
        sc for sc in generate_corpus() if sc.wellness_category == category
    )
    result = CorpusRunner(scenario).run()
    assert result.passed, result.errors
