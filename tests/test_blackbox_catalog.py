"""Tests for deterministic 500-scenario catalog (no SIP)."""

from tools.blackbox_caller.scenarios.catalog import (
    CORPUS_SEED,
    CORPUS_VERSION,
    FAMILIES,
    WELLNESS_CATEGORIES,
    catalog_size,
    generate_catalog,
)


def test_catalog_is_500_deterministic() -> None:
    a = generate_catalog()
    b = generate_catalog()
    assert len(a) == 501
    assert a[0].id == b[0].id
    assert catalog_size() == 501


def test_catalog_coverage_matrix() -> None:
    scenarios = generate_catalog()
    matrix = [s for s in scenarios if s.family in FAMILIES]
    by_cat: dict[str, int] = {}
    by_family: dict[str, int] = {}
    for s in matrix:
        by_cat[s.wellness_category] = by_cat.get(s.wellness_category, 0) + 1
        by_family[s.family] = by_family.get(s.family, 0) + 1
    assert set(by_cat) == set(WELLNESS_CATEGORIES)
    assert all(by_cat[c] == 100 for c in WELLNESS_CATEGORIES)
    assert set(by_family) == set(FAMILIES)
    assert all(by_family[f] == 25 for f in FAMILIES)
    assert any(s.id == "live-decline-no-pain" for s in scenarios)
    ladder = next(s for s in scenarios if s.id == "good-clean_short-00")
    assert "coverage_ladder" in ladder.tags
    assert "background_nutrition" in ladder.expected_intents


def test_named_mandatory_ids_present() -> None:
    ids = {s.id for s in generate_catalog()}
    assert "multi_slot_so_so_sleep_plans" in ids
    assert "contextual_horosho_wellness_vs_plans" in ids
    assert "barge_in_during_opening" in ids
    assert "live-decline-no-pain" in ids


def test_corpus_version_constant() -> None:
    assert CORPUS_VERSION == "1.1.0"
    assert CORPUS_SEED == 42
