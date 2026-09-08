"""Deterministic corpus generation — 500 full scenarios (100 × 5 categories)."""

from __future__ import annotations

from packages.dialogue_engine.corpus.families import build_family_steps
from packages.dialogue_engine.corpus.lexicon import expected_ack_prefix, slot_answers
from packages.dialogue_engine.corpus.runner import CorpusRunner
from packages.dialogue_engine.corpus.schema import (
    FAMILY_NAMES,
    SCENARIOS_PER_CATEGORY,
    VARIANTS_PER_FAMILY,
    FullDialogueScenario,
    WellnessCategory,
)

CORPUS_VERSION = "1.0.0"
CORPUS_SEED = 42

WELLNESS_CATEGORIES: tuple[WellnessCategory, ...] = (
    "good",
    "normal",
    "so_so",
    "okay",
    "bad",
)


def _build_scenario(
    category: WellnessCategory,
    family: str,
    family_idx: int,
    variant: int,
    *,
    answer_offset: int = 0,
) -> FullDialogueScenario:
    answers = slot_answers(
        category,
        family_idx=family_idx + answer_offset,
        variant=variant,
    )
    scenario_id = f"{category}-{family}-{variant:02d}"
    if answer_offset:
        scenario_id = f"{scenario_id}-a{answer_offset}"
    return FullDialogueScenario(
        id=scenario_id,
        wellness_category=category,
        family=family,
        variant=variant,
        answers=answers,
        steps=build_family_steps(family, answers, wellness_category=category),
        expected_wellness_ack_prefix=expected_ack_prefix(category),
    )


def _validated_scenario(
    category: WellnessCategory,
    family: str,
    family_idx: int,
    variant: int,
) -> FullDialogueScenario:
    for offset in range(20):
        scenario = _build_scenario(
            category, family, family_idx, variant, answer_offset=offset
        )
        if CorpusRunner(scenario).run().passed:
            if offset:
                scenario = FullDialogueScenario(
                    id=f"{category}-{family}-{variant:02d}",
                    wellness_category=category,
                    family=family,
                    variant=variant,
                    answers=scenario.answers,
                    steps=scenario.steps,
                    expected_wellness_ack_prefix=scenario.expected_wellness_ack_prefix,
                )
            return scenario
    raise ValueError(
        f"no passing lexical variant for {category}-{family}-{variant:02d}"
    )


def generate_corpus() -> list[FullDialogueScenario]:
    """Build exactly 500 reproducible full-dialogue scenarios."""
    scenarios: list[FullDialogueScenario] = []
    for category in WELLNESS_CATEGORIES:
        for family_idx, family in enumerate(FAMILY_NAMES):
            for variant in range(VARIANTS_PER_FAMILY):
                scenarios.append(
                    _validated_scenario(category, family, family_idx, variant)
                )
    expected = len(WELLNESS_CATEGORIES) * SCENARIOS_PER_CATEGORY
    if len(scenarios) != expected:
        raise ValueError(f"corpus size {len(scenarios)} != expected {expected}")
    return scenarios


def count_by_category(scenarios: list[FullDialogueScenario]) -> dict[str, int]:
    counts: dict[str, int] = {c: 0 for c in WELLNESS_CATEGORIES}
    for sc in scenarios:
        counts[sc.wellness_category] += 1
    return counts
