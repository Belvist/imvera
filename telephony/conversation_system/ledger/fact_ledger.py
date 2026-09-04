"""FactLedger — immutable facts with supersede-on-correction (Phase 6)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass(frozen=True)
class FactRecord:
    """One durable fact with optional supersession chain."""

    text: str
    turn: int = 0
    slot: str = ""
    superseded_by: str = ""


@dataclass
class FactLedger:
    """Append-only facts; corrections mark old rows superseded."""

    facts: List[FactRecord] = field(default_factory=list)

    def add(self, text: str, *, turn: int = 0, slot: str = "") -> FactRecord:
        t = (text or "").strip()
        if not t:
            raise ValueError("fact text required")
        rec = FactRecord(text=t, turn=turn, slot=(slot or "").strip())
        self.facts.append(rec)
        return rec

    def supersede(self, old_text: str, new_text: str, *, turn: int = 0) -> None:
        old = (old_text or "").strip()
        new = (new_text or "").strip()
        if not old or not new:
            return
        for i, rec in enumerate(self.facts):
            if rec.text == old and not rec.superseded_by:
                self.facts[i] = FactRecord(
                    text=rec.text,
                    turn=rec.turn,
                    slot=rec.slot,
                    superseded_by=new,
                )
                break
        self.add(new, turn=turn)

    def active_facts(self) -> Tuple[str, ...]:
        return tuple(
            f.text for f in self.facts
            if f.text and not f.superseded_by
        )
