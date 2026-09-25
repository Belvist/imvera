"""Build MissionResultSnapshot + CallOutcomes from EngineState (canonical)."""

from __future__ import annotations

from packages.contracts.enums import SlotStatus
from packages.contracts.mission_result import (
    CallOutcomes,
    GoalResultSnapshot,
    MissionResultSnapshot,
)
from packages.dialogue_engine.mission_flow import is_custom_mission
from packages.dialogue_engine.mission_seed import mission_from_state
from packages.dialogue_engine.state import EngineState, GoalLifecycle

_COMPLETED_OK = frozenset(
    {
        GoalLifecycle.SATISFIED.value,
        GoalLifecycle.NOT_APPLICABLE.value,
    }
)
_PARTIAL_FORCE = frozenset(
    {
        GoalLifecycle.SKIPPED.value,
        GoalLifecycle.UNCLEAR.value,
        GoalLifecycle.BLOCKED.value,
    }
)
_NOT_STARTED = frozenset(
    {
        GoalLifecycle.AVAILABLE.value,
        GoalLifecycle.UNSEEN.value,
        GoalLifecycle.ACTIVE.value,
    }
)

# Episodes that still describe a living complaint (resolved ones are history).
_OPEN_EPISODE = frozenset({"open", "suspended"})


def _has_open_complaints(state: EngineState) -> bool:
    """Grounded complaint evidence — no text heuristics.

    Counts speaker/unknown-subject issue episodes (other-person pain stays
    informational in observations, it must not inflate the elder's status)
    plus a probed wellness concern. Either floors care at YELLOW.
    """
    episodes = getattr(state, "issue_episodes", None) or {}
    values = episodes.values() if hasattr(episodes, "values") else episodes
    for ep in values:
        if ep is None:
            continue
        if getattr(ep, "status", "open") not in _OPEN_EPISODE:
            continue
        if getattr(ep, "subject", "unknown") == "other_person":
            continue
        return True
    if (getattr(state, "wellness_concern", "") or "").strip():
        return True
    return False


def _care_state(state: EngineState, mission_status: str):
    """Mission completion is not health evidence.

    A suffering elder with a formally completed mission must never read
    GREEN — grounded complaints floor care at YELLOW. RED still comes
    only from the safety path (Core owns verdicts).
    """
    from packages.contracts.enums import CareState

    if mission_status != "COMPLETED":
        return CareState.YELLOW
    if _has_open_complaints(state):
        return CareState.YELLOW
    return CareState.GREEN


def _grounded_evidence_quotes(state: EngineState, goal) -> list[str]:
    """Public evidence = grounded quote text only (never synthetic ev-... IDs)."""
    quotes: list[str] = []
    seen: set[str] = set()
    for eid in getattr(goal, "evidence_ids", ()) or ():
        if not isinstance(eid, str):
            continue
        obs = state.observations.get(eid) if hasattr(state.observations, "get") else None
        if obs is None:
            continue
        quote = str(getattr(obs, "evidence", "") or "").strip()
        if not quote or quote.startswith("ev-"):
            continue
        key = quote.casefold()
        if key in seen:
            continue
        seen.add(key)
        quotes.append(quote)
    return quotes


def build_mission_result(state: EngineState) -> MissionResultSnapshot:
    mission = mission_from_state(state)
    goals: list[GoalResultSnapshot] = []
    for gdef in mission.goals:
        g = state.goals.get(gdef.goal_id)
        evidence = _grounded_evidence_quotes(state, g) if g is not None else []
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
    wellness_unknown = state.observations.get("wellness_unknown")
    if isinstance(wellness_unknown, str):
        obs_notes.append(f"wellness_unknown:{wellness_unknown}")
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

    lifecycles = {g.lifecycle for g in required}
    started = any(
        g.lifecycle not in _NOT_STARTED or int(g.attempts or 0) > 0 for g in required
    )

    if state.safety_mode == "red" or state.risk_handling:
        return "PARTIAL" if started or state.safety_mode == "red" else "PARTIAL"

    if all(g.lifecycle in _NOT_STARTED and int(g.attempts or 0) == 0 for g in required):
        return "NOT_RUN"

    if all(g.lifecycle == GoalLifecycle.DECLINED.value for g in required):
        return "DECLINED"

    if all(g.lifecycle in _COMPLETED_OK for g in required):
        return "COMPLETED"

    if lifecycles & _PARTIAL_FORCE:
        return "PARTIAL" if started else "NOT_RUN"

    if GoalLifecycle.SATISFIED.value in lifecycles and GoalLifecycle.DECLINED.value in lifecycles:
        return "PARTIAL"

    if GoalLifecycle.SATISFIED.value in lifecycles:
        return "PARTIAL"

    return "PARTIAL" if started else "NOT_RUN"


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
            candidate_family_status="UNSET",
        )
    if state.closing_reason in {"stop_call", "revoke_consent", "defer"} or (
        state.call_closed and state.closing_reason
    ):
        reason = state.closing_reason or ""
        if "consent" in reason or state.closing_reason == "stop_call":
            call_out = "DECLINED"
        else:
            call_out = "COMPLETED"
    elif state.call_closed or state.fsm_state.value in {
        "GOODBYE",
        "SUMMARY",
        "FINAL_CLASSIFICATION",
    }:
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
    elif call_out == "COMPLETED" and not is_custom_mission(state):
        # P0#4: wire StatusEngine for the engine path (no legacy status).
        # A completed call is itself evidence of contact/consent/talk.
        from packages.contracts.enums import (
            ConsentState,
            DeliveryState,
            TechnicalState,
        )
        from packages.contracts.status import CallStatusSnapshot, SafetySnapshot
        from packages.status.engine import StatusEngine

        checks = {
            "identity": True,
            "consent": True,
            "can_talk": True,
            "wellness": state.slots.get("wellness") == SlotStatus.FILLED,
            "mood": state.slots.get("mood") == SlotStatus.FILLED,
            "sleep": state.slots.get("sleep") == SlotStatus.FILLED,
            "plans": state.slots.get("plans") == SlotStatus.FILLED,
        }
        snapshot = CallStatusSnapshot(
            call_id=state.call_id,
            delivery_state=DeliveryState.ANSWERED,
            technical_state=TechnicalState.OK,
            care_state=_care_state(state, mr.status),
            consent_state=ConsentState.UNKNOWN,
            safety=SafetySnapshot(),
            mandatory_checks=checks,
        )
        family = StatusEngine.resolve(snapshot).value

    return CallOutcomes(
        call_outcome=call_out,  # type: ignore[arg-type]
        mission_status=mr.status,  # type: ignore[arg-type]
        candidate_family_status=family,  # type: ignore[arg-type]
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
