"""Safety lifecycle for Golden Path — explicit phases, not a lone boolean."""
from __future__ import annotations

from enum import Enum


class SafetyPhase(str, Enum):
    INACTIVE = "INACTIVE"
    ACTIVE = "ACTIVE"
    RESOLVING = "RESOLVING"
    RESOLVED = "RESOLVED"


_IMPROVEMENT_CUES: tuple[str, ...] = (
    "лучше",
    "легче",
    "прошло",
    "уже нормально",
    "отпустило",
    "полегчало",
    "стало легче",
    "уже хорошо",
)

_DISTRESS_CUES: tuple[str, ...] = (
    "страшно",
    "боюсь",
    "паник",
    "тревож",
    "плохо мне",
    "очень плохо",
)


def is_safety_resolving_text(text: str) -> bool:
    low = (text or "").lower()
    return any(cue in low for cue in _IMPROVEMENT_CUES)


def is_distress_followup(text: str) -> bool:
    low = (text or "").lower()
    return any(cue in low for cue in _DISTRESS_CUES)
