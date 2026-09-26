"""Protocol table — single source for required/coverage/status (P0b Step 1).

Loaded once at import from pilot_checkin.yaml. Consumers must import
from here, never hardcode a second copy (see docs/plans/P0b-protocol-as-data.md).
"""

from __future__ import annotations

from pathlib import Path

import yaml

_YAML_PATH = Path(__file__).resolve().parent / "pilot_checkin.yaml"


def _load() -> dict:
    with _YAML_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError(f"bad protocol table {_YAML_PATH}")
    return data


PROTOCOL: dict = _load()
MODES: dict = PROTOCOL["modes"]
STATUS_IMPACT: dict = PROTOCOL.get("status_impact", {})
ACTS: dict = PROTOCOL.get("acts", {})

# Background = required in full but not in short (derived, not copied).
BACKGROUND_SLOTS: tuple[str, ...] = tuple(
    s for s in MODES["full"]["required_slots"] if s not in MODES["short"]["required_slots"]
)


def required_slots(mode: str) -> tuple[str, ...]:
    return tuple(MODES[mode]["required_slots"])


def coverage_order(mode: str = "full") -> tuple[str, ...]:
    return tuple(MODES[mode]["coverage_order"])
