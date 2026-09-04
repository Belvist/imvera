"""TurnDirective — structured LLM intent for one reply turn (Phase 6)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence, Tuple


@dataclass(frozen=True)
class TurnDirective:
    """Merged observer + goal + agenda constraints — no OR-merge in session."""

    observer_handling: str = ""
    goal_must_do: str = ""
    required_slot: str = ""
    required_action: str = ""
    current_slot: str = ""
    covered_slots: Tuple[str, ...] = field(default_factory=tuple)
    forbidden_slots: Tuple[str, ...] = field(default_factory=tuple)
    facts: Tuple[str, ...] = field(default_factory=tuple)
    pending_question: str = ""
    tone_policy: str = ""

    def format(self) -> str:
        """Render directive text for LLM context (compose_turn_directive output)."""
        parts: list[str] = []
        if self.observer_handling.strip():
            parts.append(f"User handling: {self.observer_handling.strip()}")
        action = (self.required_action or self.goal_must_do).strip()
        if action:
            parts.append(f"Required action: {action}")
        slot = (self.required_slot or self.current_slot).strip()
        if slot:
            parts.append(f"Required slot: {slot}")
        if self.covered_slots:
            parts.append(f"Covered: {', '.join(self.covered_slots)}")
        if self.forbidden_slots:
            parts.append(f"Never repeat: {', '.join(self.forbidden_slots)}")
        if self.facts:
            parts.append("Facts: " + "; ".join(str(f) for f in self.facts[-4:]))
        if self.pending_question.strip():
            parts.append(f"Pending question: {self.pending_question.strip()}")
        if self.tone_policy.strip():
            parts.append(f"Tone: {self.tone_policy.strip()}")
        return "\n".join(parts)

    @classmethod
    def from_parts(
        cls,
        *,
        observer_handling: str = "",
        goal_must_do: str = "",
        required_slot: str = "",
        required_action: str = "",
        current_slot: str = "",
        covered_slots: Sequence[str] = (),
        forbidden_slots: Sequence[str] = (),
        facts: Sequence[str] = (),
        pending_question: str = "",
        tone_policy: str = "",
    ) -> "TurnDirective":
        return cls(
            observer_handling=observer_handling,
            goal_must_do=goal_must_do,
            required_slot=required_slot,
            required_action=required_action,
            current_slot=current_slot,
            covered_slots=tuple(covered_slots),
            forbidden_slots=tuple(forbidden_slots),
            facts=tuple(facts),
            pending_question=pending_question,
            tone_policy=tone_policy,
        )
