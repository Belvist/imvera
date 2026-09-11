"""Build read-only MissionUnderstandingContext from EngineState (projection only)."""

from __future__ import annotations

from packages.dialogue_engine.mission_understanding import MissionUnderstandingContext
from packages.dialogue_engine.state import EngineState, QuestionPhase


def build_mission_understanding_context(state: EngineState) -> MissionUnderstandingContext:
    lifecycles: list[tuple[str, str]] = []
    answers: list[tuple[str, str, str]] = []
    for gid in state.mission_goal_ids:
        goal = state.goals.get(gid)
        if goal is None:
            continue
        lifecycles.append((gid, str(goal.lifecycle.value)))
        if goal.answer is not None:
            ev = ""
            for eid in goal.evidence_ids:
                obs = state.observations.get(eid) if isinstance(state.observations, dict) else None
                if obs is not None and getattr(obs, "evidence", None):
                    ev = str(obs.evidence)
                    break
            answers.append((gid, str(goal.answer), ev))

    delivered_goal = None
    delivered_text = None
    delivered_phase = None
    dq = state.delivered_question
    if dq is not None and dq.phase == QuestionPhase.DELIVERED:
        delivered_goal = dq.goal_id or dq.slot
        delivered_text = dq.text
        delivered_phase = dq.phase.value

    suspended = None
    if state.suspended_obligation and state.suspended_obligation.goal_id:
        suspended = state.suspended_obligation.goal_id

    episodes: list[str] = []
    for ep in state.issue_episodes.values():
        if ep.status == "resolved":
            continue
        episodes.append(f"{ep.episode_id}:{ep.kind}:{ep.primary_label}")

    return MissionUnderstandingContext(
        mission_id=state.mission_id or "",
        goal_ids=tuple(state.mission_goal_ids),
        goal_lifecycles=tuple(lifecycles),
        grounded_answers=tuple(answers),
        delivered_goal_id=delivered_goal,
        delivered_question_text=delivered_text,
        delivered_question_phase=delivered_phase,
        suspended_goal_id=suspended,
        open_episode_summaries=tuple(episodes),
    )
