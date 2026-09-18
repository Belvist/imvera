from __future__ import annotations

from packages.dialogue_engine.action_policy.actions import ActionKind
from packages.dialogue_engine.action_policy.policy import choose
from packages.dialogue_engine.action_policy.snapshot import (
    TurnContextView,
    build_policy_snapshot,
)
from packages.dialogue_engine.state import BackgroundGoalCoverage, EngineState, SlotStatus
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text


def _wellness_covered_state() -> EngineState:
    state = EngineState(call_id="safety-raw")
    state.turn_seq = 2
    state.slots["wellness"] = SlotStatus.FILLED
    state.background_goal_status["wellness"] = BackgroundGoalCoverage.ANSWERED.value
    return state


def test_raw_breathing_turn_triggers_safety_without_legacy_check_path() -> None:
    state = _wellness_covered_state()
    assert state.check_path.value != "urgent"

    rich = build_rich_turn_from_text(
        "Не могу дышать",
        utterance_id="u-safety",
        engine_state=state,
    )
    snapshot = build_policy_snapshot(state)
    assert snapshot.risk_level == "none"

    ctx = TurnContextView.from_turn(rich)
    assert ctx.urgent_risk

    decision = choose(snapshot, ctx)
    assert decision.chosen.kind == ActionKind.SAFETY
