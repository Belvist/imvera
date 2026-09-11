"""Build MissionResultSnapshot + CallOutcomes from EngineState (canonical)."""

from __future__ import annotations

from packages.contracts.mission_result import (
    CallOutcomes,
    GoalResultSnapshot,
    MissionResultSnapshot,
)
from packages.dialogue_engine.mission_flow import is_custom_mission
from packages.dialogue_engine.mission_seed import mission_from_state
from packages.dialogue_engine.state import EngineState, GoalLifecycle

_TERMINAL_OK = frozenset(
    {
        GoalLifecycle.SATISFIED,
        GoalLifecycle.DECLINED,
        GoalLifecycle.SKIPPED,
        GoalLifecycle.NOT_APPLICABLE,
    }
)


def build_mission_result(state: EngineState) -> MissionResultSnapshot:
    mission = mission_from_state(state)
    goals: list[GoalResultSnapshot] = []
    for gdef in mission.goals:
        g = state.goals.get(gdef.goal_id)
        evidence: list[str] = []
        if g is not None:
            for eid in g.evidence_ids:
                obs = state.observations.get(eid) if hasattr(state.observations, "get") else None
                if obs is not None and getattr(obs, "evidence", None):
                    evidence.append(str(obs.evidence))
                elif isinstance(eid, str) and eid.startswith("ev-"):
                    evidence.append(eid)
            if g.answer and not evidence:
                evidence.append(str(g.answer))
        goals.append(
            GoalResultSnapshot(
                goal_id=gdef.goal_id,
                lifecycle=(g.lifecycle.value if g else GoalLifecycle.AVAILABLE.value),
                value=g.answer if g else None,
                attempts=int(g.delivered_attempts) if g else 0,
                evidence=evidence,
                required=bool(gdef.required),
            )
        )

    status = _mission_status(state, goals, mission)
    obs_notes = [
        f"{o.attribute}:{o.value}"
        for o in (state.observations.values() if state.observations else [])
        if getattr(o, "attribute", None) and getattr(o, "value", None)
    ][:40]
    issues = [
        f"{ep.kind}:{ep.primary_label}:{ep.status}"
        for ep in state.issue_episodes.values()
    ]
    return MissionResultSnapshot(
        mission_id=mission.mission_id or state.mission_id or "",
        status=status,
        goals=goals,
        observations=obs_notes,
        issue_summaries=issues,
    )


def _mission_status(state: EngineState, goals: list[GoalResultSnapshot], mission) -> str:
    if getattr(state, "target_presence", None) == "unavailable":
        return "NOT_RUN"
    if not goals:
        return "NOT_RUN"
    required = [g for g, d in zip(goals, mission.goals) if d.required]
    if not required:
        required = goals
    if all(g.lifecycle == GoalLifecycle.DECLINED.value for g in required):
        return "DECLINED"
    if all(g.lifecycle in {x.value for x in _TERMINAL_OK} for g in required):
        if any(g.lifecycle == GoalLifecycle.SATISFIED.value for g in required):
            return "COMPLETED"
        return "COMPLETED"
    if any(g.lifecycle == GoalLifecycle.SATISFIED.value for g in required):
        return "PARTIAL"
    if state.safety_mode == "red" or state.risk_handling:
        return "PARTIAL"
    return "NOT_RUN" if all(g.lifecycle == GoalLifecycle.AVAILABLE.value for g in goals) else "PARTIAL"


def build_call_outcomes(
    state: EngineState,
    *,
    mission_result: MissionResultSnapshot | None = None,
    legacy_public_status: str | None = None,
) -> CallOutcomes:
    mr = mission_result or build_mission_result(state)
    if state.target_presence == "unavailable":
        return CallOutcomes(
            call_outcome="NO_ANSWER",
            mission_status="NOT_RUN",
            family_status="UNSET",
        )
    if state.closing_reason in {"stop_call", "revoke_consent", "defer"} or (
        state.call_closed and state.closing_reason
    ):
        call_out = "DECLINED" if "consent" in (state.closing_reason or "") or state.closing_reason == "stop_call" else "COMPLETED"
    elif state.call_closed or state.fsm_state.value in {"GOODBYE", "SUMMARY", "FINAL_CLASSIFICATION"}:
        call_out = "COMPLETED"
    else:
        call_out = "TECHNICAL"

    family = "UNSET"
    if state.safety_mode == "red" or state.risk_handling:
        family = "RED"
    elif legacy_public_status in {"RED", "YELLOW", "GREEN"} and not is_custom_mission(state):
        family = legacy_public_status  # type: ignore[assignment]
    elif is_custom_mission(state):
        # Custom non-care missions do not invent GREEN from answered goals.
        family = "RED" if family == "RED" else "UNSET"
    elif legacy_public_status:
        family = legacy_public_status  # type: ignore[assignment]

    return CallOutcomes(
        call_outcome=call_out,  # type: ignore[arg-type]
        mission_status=mr.status,  # type: ignore[arg-type]
        family_status=family,  # type: ignore[arg-type]
    )


def mission_context_for_llm(state: EngineState):
    from packages.contracts.semantic import MissionContextSnapshot
    from packages.dialogue_engine.mission_context import build_mission_understanding_context

    ctx = build_mission_understanding_context(state)
    mission = mission_from_state(state)
    defs = tuple(
        {
            "goal_id": g.goal_id,
            "prompt_hint": g.prompt_hint,
            "answer_type": g.answer_type,
            "allowed_values": list(g.allowed_values),
            "required": g.required,
            "priority": g.priority,
        }
        for g in mission.goals
    )
    return MissionContextSnapshot(
        mission_id=ctx.mission_id,
        goal_definitions=defs,
        goal_lifecycles=ctx.goal_lifecycles,
        grounded_answers=tuple((a[0], a[1]) for a in ctx.grounded_answers),
        delivered_goal_id=ctx.delivered_goal_id,
        delivered_question=ctx.delivered_question_text,
        suspended_goal_id=ctx.suspended_goal_id,
        open_issue_summaries=ctx.open_episode_summaries,
    )
