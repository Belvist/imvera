"""Wellness dialogue matrix — re-export of production corpus (500 scenarios).

Canonical generator: ``packages.dialogue_engine.corpus``.
Each scenario is a full FSM trajectory with DeliverPlayout / repair / stale steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from packages.dialogue_engine.corpus.generator import (
    CORPUS_SEED as MATRIX_SEED,
)
from packages.dialogue_engine.corpus.generator import (
    CORPUS_VERSION,
    SCENARIOS_PER_CATEGORY,
    WELLNESS_CATEGORIES,
    generate_corpus,
)
from packages.dialogue_engine.corpus.schema import (
    FAMILY_NAMES,
    FullDialogueScenario,
    UserStep,
)

WellnessBucket = Literal["bad", "good", "normal", "so_so", "okay"]

SCENARIOS_PER_BUCKET = SCENARIOS_PER_CATEGORY  # 100 per category


@dataclass(frozen=True)
class WellnessFullScenario:
    """Legacy flat view — user texts only (clean_short family subset)."""

    id: str
    bucket: WellnessBucket
    wellness: str
    mood: str
    sleep: str
    plans: str
    goodbye: str
    confirm: str
    expected_wellness_ack_prefix: str
    family: str = "clean_short"
    full: FullDialogueScenario | None = None


def _flat_from_full(scenario: FullDialogueScenario) -> WellnessFullScenario:
    a = scenario.answers
    return WellnessFullScenario(
        id=scenario.id,
        bucket=scenario.wellness_category,  # type: ignore[arg-type]
        wellness=a.wellness,
        mood=a.mood,
        sleep=a.sleep,
        plans=a.plans,
        goodbye=a.goodbye,
        confirm=a.confirm,
        expected_wellness_ack_prefix=scenario.expected_wellness_ack_prefix,
        family=scenario.family,
        full=scenario,
    )


def generate_wellness_matrix(
    *,
    per_bucket: int = SCENARIOS_PER_BUCKET,
) -> list[WellnessFullScenario]:
    """Return flat scenarios for clean_short family (100 total, one per category)."""
    if per_bucket != SCENARIOS_PER_CATEGORY:
        raise ValueError(f"per_bucket must be {SCENARIOS_PER_CATEGORY}")
    corpus = generate_corpus()
    clean = [s for s in corpus if s.family == "clean_short"]
    return [_flat_from_full(s) for s in clean]


def all_wellness_scenarios() -> list[FullDialogueScenario]:
    """Full 500-scenario production corpus."""
    return generate_corpus()


def matrix_count_by_bucket(
    scenarios: list[FullDialogueScenario] | list[WellnessFullScenario],
) -> dict[str, int]:
    counts: dict[str, int] = {c: 0 for c in WELLNESS_CATEGORIES}
    for sc in scenarios:
        bucket = sc.wellness_category if isinstance(sc, FullDialogueScenario) else sc.bucket
        counts[bucket] += 1
    return counts


def user_texts(scenario: FullDialogueScenario) -> list[str]:
    """Extract user utterances from a full scenario (debug helper)."""
    return [s.text for s in scenario.steps if isinstance(s, UserStep)]


__all__ = [
    "CORPUS_VERSION",
    "FAMILY_NAMES",
    "MATRIX_SEED",
    "SCENARIOS_PER_BUCKET",
    "WELLNESS_CATEGORIES",
    "WellnessBucket",
    "WellnessFullScenario",
    "all_wellness_scenarios",
    "generate_wellness_matrix",
    "matrix_count_by_bucket",
    "user_texts",
]
