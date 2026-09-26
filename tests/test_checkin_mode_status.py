"""Live fs-e98331b8: all-good short call must be GREEN, not YELLOW.

Required-ness follows the check-in mode: short mode (default) does not
require bg goals it never asks; full mode (mission-required bg goals)
does. Same engine, same honesty — mode-aware gates.
"""

from __future__ import annotations

import pytest

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.engine import DialogueEngine
from packages.dialogue_engine.mission_result import (
    build_call_outcomes,
    build_mission_result,
)

pytestmark = pytest.mark.dialogue_engine


def _short_all_good() -> DialogueEngine:
    from packages.dialogue_engine.state import GoalLifecycle

    engine = DialogueEngine(call_id="mode-short", elder_display_name="Тест")
    engine.start()
    engine.state.call_closed = True
    for slot, value in (
        ("wellness", "хорошо"),
        ("mood", "супер"),
        ("sleep", "выспался"),
    ):
        engine.state.slots[slot] = SlotStatus.FILLED
        engine.state.slot_values[slot] = value
        goal = engine.state.ensure_goal(slot)
        goal.lifecycle = GoalLifecycle.SATISFIED
        goal.answer = value
    return engine


def test_short_all_good_is_completed_green() -> None:
    engine = _short_all_good()
    snapshot = build_mission_result(engine.state)
    assert snapshot.status == "COMPLETED"
    outcomes = build_call_outcomes(engine.state)
    assert outcomes.mission_status == "COMPLETED"
    assert outcomes.candidate_family_status == "GREEN"


def test_full_mode_with_open_plans_is_partial_yellow() -> None:
    engine = _short_all_good()
    engine.state.required_background_goals = {"mood", "sleep", "plans"}
    snapshot = build_mission_result(engine.state)
    assert snapshot.status == "PARTIAL"
    outcomes = build_call_outcomes(engine.state)
    assert outcomes.mission_status == "PARTIAL"
    assert outcomes.candidate_family_status == "YELLOW"


def test_short_mode_ignores_unasked_plans_in_mandatory() -> None:
    from packages.status.engine import StatusEngine

    engine = _short_all_good()
    outcomes = build_call_outcomes(engine.state)
    assert outcomes.candidate_family_status == "GREEN"
    _ = StatusEngine
