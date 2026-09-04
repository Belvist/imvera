"""Which planner actions skip LLM phrase rendering."""
from __future__ import annotations

from golden_path.analyzer import AnswerType
from golden_path.planner import Plan, PlannerAction

CONTROL_ACTIONS_NO_LLM: frozenset[PlannerAction] = frozenset(
    {
        PlannerAction.WAIT,
        PlannerAction.CLOSE,
        PlannerAction.HANDLE_REFUSAL,
        PlannerAction.HANDLE_CORRECTION,
        PlannerAction.REPAIR,
        PlannerAction.HANDLE_FATIGUE,
        PlannerAction.SAFETY,
    }
)


def plan_uses_llm_renderer(plan: Plan) -> bool:
    if plan.action in CONTROL_ACTIONS_NO_LLM:
        return False
    if plan.action == PlannerAction.ANSWER_USER and plan.answer_type in (
        AnswerType.IDENTITY,
        AnswerType.PRIVACY,
        AnswerType.WHY_CALLING,
    ):
        return False
    return True
