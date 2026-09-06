"""Pilot mandatory checks — single source of truth (DIALOGUE_SPEC)."""

PILOT_MANDATORY_CHECKS: tuple[str, ...] = (
    "identity",
    "consent",
    "can_talk",
    "wellness",
    "mood",
    "sleep",
    "plans",
)

PILOT_SLOT_CHECKS: tuple[str, ...] = ("wellness", "mood", "sleep", "plans")


def pilot_mandatory_defaults() -> dict[str, bool]:
    return {key: False for key in PILOT_MANDATORY_CHECKS}
