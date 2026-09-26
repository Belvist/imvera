"""Pilot mandatory checks — values owned by the protocol table.

Single source: packages/dialogue_engine/protocol/pilot_checkin.yaml
(modes.full.required_slots). This module keeps literals (contracts layer
must not import the engine) — equality is pinned by
tests/test_protocol_table.py::test_constants_match_yaml. Edit YAML first.
"""

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
