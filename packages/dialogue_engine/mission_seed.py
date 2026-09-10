"""Seed EngineState from CallMission — no separate mission store."""

from __future__ import annotations

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.mission import CallMission, GoalDefinition, daily_check_mission
from packages.dialogue_engine.state import EngineState, GoalLifecycle, GoalState

_DAILY_SLOTS = frozenset({"wellness", "mood", "sleep", "plans"})


def apply_mission_to_state(state: EngineState, mission: CallMission) -> None:
    """Attach mission metadata and seed GoalState entries from GoalDefinitions."""
    state.mission_id = mission.mission_id
    state.mission_preset = mission.preset
    state.mission_goal_ids = tuple(g.goal_id for g in mission.goals)
    state.mission_catalog = tuple(mission.goals)

    for gdef in mission.goals:
        _seed_goal(state, gdef, source=mission.preset or "mission")


def mission_from_state(state: EngineState) -> CallMission:
    """Rehydrate CallMission view from EngineState catalog snapshot."""
    catalog = tuple(state.mission_catalog or ())
    return CallMission(
        mission_id=state.mission_id or "daily_check",
        goals=catalog,
        preset=state.mission_preset,
    )


def _seed_goal(state: EngineState, gdef: GoalDefinition, *, source: str) -> None:
    existing = state.goals.get(gdef.goal_id)
    if existing is None:
        state.goals[gdef.goal_id] = GoalState(
            slot=gdef.goal_id,
            goal_id=gdef.goal_id,
            status=SlotStatus.OPEN,
            lifecycle=GoalLifecycle.AVAILABLE,
            source=source,
        )
    else:
        existing.goal_id = gdef.goal_id
        if not existing.source:
            existing.source = source
        if existing.lifecycle == GoalLifecycle.UNSEEN:
            existing.lifecycle = GoalLifecycle.AVAILABLE

    if gdef.goal_id in _DAILY_SLOTS:
        state.slots.setdefault(gdef.goal_id, SlotStatus.OPEN)


def resolve_mission(mission: CallMission | None) -> CallMission:
    return mission if mission is not None else daily_check_mission()
