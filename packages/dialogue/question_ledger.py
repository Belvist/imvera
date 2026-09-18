"""Question goal ledger — semantic attempt tracking per spec §10."""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from packages.contracts.enums import GoalStatus, SlotStatus
from packages.contracts.mandatory import PILOT_SLOT_CHECKS

MAX_AUTOMATIC_ATTEMPTS = 2

_SLOT_SEMANTIC_KEYS: dict[str, str] = {
    "wellness": "wellness:current_report",
    "mood": "mood:current",
    "sleep": "sleep:last_night",
    "plans": "plans:today",
}

_SLOT_CLARIFICATIONS: dict[str, str] = {
    "wellness": "Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.",
    "mood": "Как у вас настроение — хотя бы коротко?",
    "sleep": "Как вы спали — коротко, пожалуйста?",
    "plans": "Какие у вас планы на сегодня — в двух словах?",
}


class QuestionGoal(BaseModel):
    goal_id: str
    semantic_key: str
    topic_slot: str
    status: GoalStatus = GoalStatus.OPEN
    automatic_attempts_used: int = 0
    max_automatic_attempts: int = MAX_AUTOMATIC_ATTEMPTS
    reserved_attempt_id: str | None = None
    last_question_id: str | None = None
    last_delivery_state: str = "unknown"
    audio_may_have_reached_channel: bool = False


def semantic_key_for_slot(slot: str) -> str:
    return _SLOT_SEMANTIC_KEYS.get(slot, f"{slot}:current")


def clarification_for_slot(slot: str) -> str:
    return _SLOT_CLARIFICATIONS.get(slot, "Повторите, пожалуйста, коротко.")


def new_goal(slot: str) -> QuestionGoal:
    return QuestionGoal(
        goal_id=f"goal-{uuid.uuid4().hex[:12]}",
        semantic_key=semantic_key_for_slot(slot),
        topic_slot=slot,
    )


def slot_status_from_goal(goal: QuestionGoal) -> SlotStatus:
    if goal.status == GoalStatus.ANSWERED:
        return SlotStatus.FILLED
    if goal.status == GoalStatus.DECLINED:
        return SlotStatus.DECLINED
    if goal.status == GoalStatus.UNRESOLVED:
        return SlotStatus.UNRESOLVED
    return SlotStatus.OPEN


def is_slot_collectable(slots: dict[str, SlotStatus], slot: str) -> bool:
    return slots.get(slot) == SlotStatus.OPEN


def next_open_slot(slots: dict[str, SlotStatus]) -> str | None:
    for slot in PILOT_SLOT_CHECKS:
        if is_slot_collectable(slots, slot):
            return slot
    return None
