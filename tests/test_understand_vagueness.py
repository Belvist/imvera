"""Understanding must translate human vagueness precisely (live fs-6e3abff0).

- "Ничего не болит, всё хорошо." is POSITIVE, not negative.
- "Да так пойдёт." is wellness-uncertain, never a plans fact.
- "И ничего вроде не беспокоит." declines the concern probe (no re-ask).
"""

from __future__ import annotations

import pytest

from packages.dialogue_engine.issue_mention_extract import extract_goal_facts

pytestmark = pytest.mark.dialogue_engine


def _fields(text: str, slot: str | None = "wellness"):
    return [(f.field, f.value) for f in extract_goal_facts(text, answer_slot=slot)]


def test_denied_pain_with_positive_is_positive() -> None:
    assert ("wellness", "positive") in _fields("Ничего не болит, всё хорошо.")
    assert ("wellness", "negative") not in _fields("Ничего не болит, всё хорошо.")


def test_so_so_is_uncertain_never_plans() -> None:
    fields = _fields("Да так пойдёт.")
    assert ("wellness", "uncertain") in fields
    assert "plans" not in [f for f, _ in fields]


def test_nothing_bothers_declines_concern() -> None:
    from packages.dialogue_engine.check_path import apply_concern_answer
    from packages.dialogue_engine.state import EngineState

    state = EngineState(call_id="x", elder_display_name="Т")
    assert apply_concern_answer(state, "И ничего вроде не беспокоит.") == "declined"
    assert apply_concern_answer(state, "Ничего не болит, всё хорошо.") == "declined"


def test_real_complaint_still_grounds() -> None:
    from packages.dialogue_engine.check_path import apply_concern_answer
    from packages.dialogue_engine.state import EngineState

    state = EngineState(call_id="x", elder_display_name="Т")
    assert apply_concern_answer(state, "Голова болит.") == "grounded"
    state2 = EngineState(call_id="y", elder_display_name="Т")
    assert (
        apply_concern_answer(state2, "Не очень, голова болит.") == "grounded"
    )


def test_explicit_decline_vs_vague_vs_refusal() -> None:
    from packages.dialogue_engine.check_path import is_explicit_concern_decline
    from packages.dialogue_engine.protocol.acts import declines_open_concern_probe

    assert is_explicit_concern_decline("И ничего вроде не беспокоит.") is True
    assert is_explicit_concern_decline("Ничего не болит, всё хорошо.") is True
    # Denial shapes only — bare positives ride the normal answer flow.
    assert is_explicit_concern_decline("Нормально.") is False
    assert is_explicit_concern_decline("Поел.") is False
    assert is_explicit_concern_decline("Не скажу.") is False
    assert is_explicit_concern_decline("Отстань.") is False
    assert is_explicit_concern_decline("Голова болит.") is False
    assert is_explicit_concern_decline("Не очень, голова болит.") is False
    assert callable(declines_open_concern_probe)
