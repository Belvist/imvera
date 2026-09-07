"""Scenario models for the 1k dialogue corpus."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Scenario:
    """One multi-turn dialogue case with expected outcomes.

    Layer: CallSession + rule interpreter (and optional fixture semantics).
    NOT live SIP / STT / TTS / PSTN.
    """

    id: str
    category: str
    turns: tuple[str, ...]
    # Final slot statuses after all turns (SlotStatus value strings).
    expect_slots: dict[str, str] = field(default_factory=dict)
    # After the last turn, intent must be one of these (if non-empty).
    expect_intent_in: tuple[str, ...] = ()
    # Slots that must remain OPEN after every turn listed (hard anti-fill).
    never_fill: tuple[str, ...] = ()
    # If True, start session already in DAILY_CHECK with pending wellness.
    start_daily: bool = True
    # Optional pre-scripted setup turns (answers) before the measured turns.
    setup_turns: tuple[str, ...] = ()
    # Soft notes for reports (not asserted).
    notes: str = ""
    # Path label for honesty in reports.
    path: str = "rule_interpreter"


@dataclass
class TurnTrace:
    user_text: str
    intent: str
    judgement: str
    dialogue_act: str
    pending_slot: str | None
    slots: dict[str, str]
    speech: str


@dataclass
class ScenarioResult:
    scenario_id: str
    category: str
    ok: bool
    errors: list[str] = field(default_factory=list)
    turns: list[TurnTrace] = field(default_factory=list)
    elapsed_ms: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)
