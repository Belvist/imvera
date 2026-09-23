"""Utility-scored coverage: person's topic beats line position, ties → order."""

from __future__ import annotations

import pytest

from packages.dialogue_engine.coverage import score_domain, scored_next_domain

pytestmark = pytest.mark.dialogue_engine


def _fresh_state():
    from packages.dialogue_engine.engine import DialogueEngine

    engine = DialogueEngine(call_id="scored", elder_display_name="Тест")
    engine.start()
    return engine.state


def test_thread_bonus_wins_over_line() -> None:
    state = _fresh_state()
    assert scored_next_domain(state, "Плохо спал, до двух читал.") == "sleep"
    state2 = _fresh_state()
    assert (
        scored_next_domain(state2, "Таблетку выпил утром.") == "medication"
    )
    state3 = _fresh_state()
    assert scored_next_domain(state3, "Настроение хорошее.") == "mood"


def test_tie_falls_back_to_filler_order() -> None:
    state = _fresh_state()
    assert scored_next_domain(state, "Привет.") == "nutrition"
    assert scored_next_domain(state, "") == "nutrition"


def test_covered_and_asked_excluded() -> None:
    state = _fresh_state()
    state.coverage_asked_domains.add("nutrition")
    assert scored_next_domain(state, "Привет.") == "medication"


def test_score_breakdown_explainable() -> None:
    score, feats = score_domain("sleep", last_user_text="плохо спал", order_index=3)
    assert feats["thread"] == 2.0
    assert score == 1.0 + 2.0 - 0.3
    score2, feats2 = score_domain("nutrition", last_user_text="плохо спал", order_index=0)
    assert feats2["thread"] == 0.0
    assert score > score2
