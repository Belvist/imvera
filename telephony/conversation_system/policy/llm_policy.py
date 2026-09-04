"""Check-in LLM gate — MOSS_DIALOGUE_LLM_CHECKIN (default pools-only)."""
from __future__ import annotations

import os

from conversation_system.domain.understanding import ResponseGoal, ResponseGoalKind

# Side-question, repair, narrative — keep LLM when env is off.
_LLM_EXEMPT_KINDS = frozenset({
    ResponseGoalKind.ANSWER_SIDE,
    ResponseGoalKind.REPAIR,
})

# Wellness / agenda turns forced to scripted pools when check-in LLM is off.
_CHECKIN_KINDS = frozenset({
    ResponseGoalKind.ASK_TOPIC,
    ResponseGoalKind.SYMPTOM_FOLLOWUP,
    ResponseGoalKind.ACKNOWLEDGE,
})


def dialogue_llm_checkin_enabled() -> bool:
    """True when hybrid LLM on wellness/agenda turns is explicitly enabled."""
    return os.environ.get("MOSS_DIALOGUE_LLM_CHECKIN", "0").strip() == "1"


def is_checkin_llm_blocked(goal: ResponseGoal) -> bool:
    """Whether this goal must use pools only (check-in path, env off)."""
    if dialogue_llm_checkin_enabled():
        return False
    if goal.kind in _LLM_EXEMPT_KINDS:
        return False
    if goal.kind == ResponseGoalKind.ACKNOWLEDGE and goal.topic == "narrative":
        return False
    return goal.kind in _CHECKIN_KINDS


def gate_checkin_llm(
    goal: ResponseGoal,
    allow_llm: bool,
) -> tuple[ResponseGoal, bool]:
    """Apply MOSS_DIALOGUE_LLM_CHECKIN to goal and allow_llm flag."""
    if not allow_llm or not is_checkin_llm_blocked(goal):
        return goal, allow_llm
    gated = ResponseGoal(
        kind=goal.kind,
        topic=goal.topic,
        symptom_focus=goal.symptom_focus,
        allow_llm=False,
        scripted_only=goal.scripted_only,
        must_do=goal.must_do,
        forbidden=goal.forbidden,
        next_topic=goal.next_topic,
    )
    return gated, False
