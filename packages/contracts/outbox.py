"""Action outbox delivery statuses (spec §15)."""

from enum import StrEnum

from pydantic import BaseModel


class ActionOutboxStatus(StrEnum):
    PENDING = "PENDING"
    DISPATCHING = "DISPATCHING"
    TRANSPORT_COMPLETE = "TRANSPORT_COMPLETE"
    DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"
    CANCELLED = "CANCELLED"


_ALLOWED_TRANSITIONS: dict[ActionOutboxStatus, frozenset[ActionOutboxStatus]] = {
    ActionOutboxStatus.PENDING: frozenset(
        {ActionOutboxStatus.DISPATCHING, ActionOutboxStatus.CANCELLED}
    ),
    ActionOutboxStatus.DISPATCHING: frozenset(
        {
            ActionOutboxStatus.TRANSPORT_COMPLETE,
            ActionOutboxStatus.DELIVERY_UNKNOWN,
            ActionOutboxStatus.CANCELLED,
        }
    ),
    ActionOutboxStatus.TRANSPORT_COMPLETE: frozenset(),
    ActionOutboxStatus.DELIVERY_UNKNOWN: frozenset(),
    ActionOutboxStatus.CANCELLED: frozenset(),
}


class OutboxRecord(BaseModel):
    action_id: str
    call_id: str
    turn_id: int
    intent: str
    speech: str
    question_goal_id: str | None = None
    state_version: int
    status: ActionOutboxStatus = ActionOutboxStatus.PENDING
    sent_samples: int = 0

    model_config = {"frozen": True}


def can_transition(current: ActionOutboxStatus, target: ActionOutboxStatus) -> bool:
    return target in _ALLOWED_TRANSITIONS.get(current, frozenset())


def apply_transition(record: OutboxRecord, target: ActionOutboxStatus) -> OutboxRecord | None:
    if not can_transition(record.status, target):
        return None
    updates: dict = {"status": target}
    return record.model_copy(update=updates)


def may_auto_replay(status: ActionOutboxStatus) -> bool:
    """DELIVERY_UNKNOWN must not return to PENDING for automatic replay."""
    return status == ActionOutboxStatus.PENDING
