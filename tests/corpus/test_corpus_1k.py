"""Pytest gate: ≥1000 dialogue scenarios via CallSession (not live SIP)."""

from __future__ import annotations

from tests.corpus.execute import run_scenario
from tests.corpus.generate import CORPUS_SEED, generate_scenarios, scenario_count_by_category
from tests.corpus.invariants import check_status_invariants


def test_corpus_size_and_categories() -> None:
    scenarios = generate_scenarios(seed=CORPUS_SEED, minimum=1000)
    assert len(scenarios) >= 1000
    cats = scenario_count_by_category(scenarios)
    required = {
        "wellness_mood",
        "backchannel",
        "full_chain",
        "who_are_you",
        "pause_stop",
        "topic_refuse",
        "complaint",
        "mixed",
        "empty_noise",
        "clarify",
        "stt_noise_nofill",
        "slot_variants",
    }
    missing = required - set(cats)
    assert not missing, f"missing categories: {missing}"


def test_status_engine_technical_never_green() -> None:
    errors = check_status_invariants()
    assert not errors, errors


def test_corpus_all_scenarios_pass() -> None:
    """Full 1k corpus gate — prefer ``make test-corpus-1k`` for throughput report."""
    scenarios = generate_scenarios(seed=CORPUS_SEED, minimum=1000)
    failures: list[str] = []
    for scenario in scenarios:
        result = run_scenario(scenario)
        if not result.ok:
            failures.append(f"{scenario.id} ({scenario.category}): {result.errors}")
            if len(failures) >= 15:
                break
    assert not failures, "corpus failures:\n" + "\n".join(failures)
