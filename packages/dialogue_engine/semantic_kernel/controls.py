"""Canonical control contract — single enum across Kernel and DialogueEngine."""

from __future__ import annotations

from dataclasses import dataclass

CANONICAL_CONTROLS = frozenset(
    {
        "none",
        "stop_call",
        "revoke_consent",
        "defer",
        "wrong_person",
        "pause",
    }
)

# Exact phrase → (dialogue_act, control). yes/no/repeat/unknown are NOT controls.
_LEVEL0_EXACT: dict[str, tuple[str, str]] = {
    "угу": ("backchannel", "none"),
    "ага": ("backchannel", "none"),
    "мм": ("backchannel", "none"),
    "ммм": ("backchannel", "none"),
    "стоп": ("answer", "stop_call"),
    "хватит": ("answer", "stop_call"),
    "остановите": ("answer", "stop_call"),
    "позже": ("answer", "defer"),
    "не хочу разговаривать": ("answer", "revoke_consent"),
    "не хочу": ("answer", "revoke_consent"),
    "не ваш человек": ("answer", "wrong_person"),
    "не тот номер": ("answer", "wrong_person"),
}


@dataclass(frozen=True)
class Level0Match:
    dialogue_act: str
    control: str


def match_level0(text: str) -> Level0Match | None:
    norm = text.strip().lower()
    if not norm:
        return None
    for phrase, (act, control) in sorted(_LEVEL0_EXACT.items(), key=lambda x: -len(x[0])):
        if norm == phrase or norm.startswith(phrase + " "):
            return Level0Match(dialogue_act=act, control=control)
    return None


def normalize_control(value: str) -> str:
    if value in CANONICAL_CONTROLS:
        return value
    legacy = {
        "stop": "stop_call",
        "refuse": "revoke_consent",
        "yes": "none",
        "no": "none",
        "unknown": "none",
        "repeat": "none",
        "backchannel": "none",
    }
    return legacy.get(value, "none")
