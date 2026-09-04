"""Slot definitions for Vera Golden Path check-in."""
from __future__ import annotations

from enum import Enum
from typing import Iterable

class SlotName(str, Enum):
    """Check-in topics in fixed order."""

    WELLNESS = "wellness"
    MOOD = "mood"
    SLEEP = "sleep"
    PLANS = "plans"


class SlotStatus(str, Enum):
    """Per-slot lifecycle."""

    OPEN = "OPEN"
    ANSWERED = "ANSWERED"
    DECLINED = "DECLINED"


SLOT_ORDER: tuple[SlotName, ...] = (
    SlotName.WELLNESS,
    SlotName.MOOD,
    SlotName.SLEEP,
    SlotName.PLANS,
)

SLOT_LABELS_RU: dict[SlotName, str] = {
    SlotName.WELLNESS: "самочувствие",
    SlotName.MOOD: "настроение",
    SlotName.SLEEP: "сон",
    SlotName.PLANS: "планы",
}

REFUSAL_MARKERS: tuple[str, ...] = (
    "не хочу",
    "не буду",
    "не надо",
    "не скажу",
    "не буду говорить",
    "давайте без этого",
    "пропустим",
    "неважно",
    "не важно",
    "не хочу об этом",
    "не буду отвечать",
)


def default_slot_map() -> dict[SlotName, SlotStatus]:
    return {slot: SlotStatus.OPEN for slot in SLOT_ORDER}


def answered_slots(statuses: dict[SlotName, SlotStatus]) -> list[SlotName]:
    return [s for s in SLOT_ORDER if statuses.get(s) == SlotStatus.ANSWERED]


def declined_slots(statuses: dict[SlotName, SlotStatus]) -> list[SlotName]:
    return [s for s in SLOT_ORDER if statuses.get(s) == SlotStatus.DECLINED]


def closed_slots(statuses: dict[SlotName, SlotStatus]) -> list[SlotName]:
    return [
        s for s in SLOT_ORDER
        if statuses.get(s) in (SlotStatus.ANSWERED, SlotStatus.DECLINED)
    ]


def next_open_slot(statuses: dict[SlotName, SlotStatus]) -> SlotName | None:
    for slot in SLOT_ORDER:
        if statuses.get(slot, SlotStatus.OPEN) == SlotStatus.OPEN:
            return slot
    return None


def may_ask_slot(slot: SlotName, statuses: dict[SlotName, SlotStatus]) -> bool:
    status = statuses.get(slot, SlotStatus.OPEN)
    return status == SlotStatus.OPEN


def is_refusal(text: str, slot: SlotName | None = None) -> bool:
    low = text.lower()
    if any(marker in low for marker in REFUSAL_MARKERS):
        return True
    if slot is not None:
        label = SLOT_LABELS_RU[slot]
        if f"не про {label}" in low or f"без {label}" in low:
            return True
    return False


def format_slot_list(slots: Iterable[SlotName]) -> str:
    return ", ".join(s.value for s in slots)


__all__ = [
    "SlotName",
    "SlotStatus",
    "SLOT_ORDER",
    "SLOT_LABELS_RU",
    "REFUSAL_MARKERS",
    "default_slot_map",
    "answered_slots",
    "declined_slots",
    "closed_slots",
    "next_open_slot",
    "may_ask_slot",
    "is_refusal",
    "format_slot_list",
]
