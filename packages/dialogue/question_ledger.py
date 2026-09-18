"""Question goal ledger — semantic attempt tracking per spec §10."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

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


def reserve_question_attempt(state: Any, generation_id: str, slot: str) -> bool:
    """Reserve one legacy question attempt; ledger owns delivery accounting."""
    goal = state.ensure_goal(slot)
    if goal.status != GoalStatus.OPEN:
        return False
    if goal.reserved_attempt_id == generation_id:
        return True
    if goal.reserved_attempt_id is not None:
        return False
    if goal.automatic_attempts_used >= goal.max_automatic_attempts:
        return False
    goal.reserved_attempt_id = generation_id
    state.pending_action_id = generation_id
    state.bump_version()
    return True


def mark_question_delivered(state: Any, generation_id: str) -> None:
    """Count a legacy attempt only once audio may have reached the channel."""
    slot = state.pending_slot
    if not slot:
        return
    goal = state.get_goal(slot)
    if goal is None or goal.reserved_attempt_id != generation_id:
        return
    if goal.automatic_attempts_used < goal.max_automatic_attempts:
        goal.automatic_attempts_used += 1
    goal.last_question_id = generation_id
    goal.last_delivery_state = "may_have_reached_channel"
    goal.audio_may_have_reached_channel = True
    goal.reserved_attempt_id = None
    state.pending_question_delivered = True
    state.delivered_answer_slot = slot
    state.pending_action_id = None
    if slot == "wellness" and state.opening_play_count > 0:
        state.opening_delivered = True
    state.bump_version()


def release_question_attempt(state: Any, generation_id: str) -> None:
    """Release a legacy reservation when no audio reached the channel."""
    slot = state.pending_slot
    if not slot:
        return
    goal = state.get_goal(slot)
    if goal is None or goal.reserved_attempt_id != generation_id:
        return
    goal.reserved_attempt_id = None
    if state.pending_action_id == generation_id:
        state.pending_action_id = None
    state.bump_version()
