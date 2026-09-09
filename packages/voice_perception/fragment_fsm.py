"""Bounded fragment hold FSM — no eternal or cross-call merges."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# Tuned for current endpointing (~500–1200ms continuation window).
FRAGMENT_HOLD_TIMEOUT_MS = 900


class FragmentPhase(StrEnum):
    EMPTY = "EMPTY"
    HELD = "HELD"
    EXPIRED = "EXPIRED"


@dataclass
class FragmentState:
    phase: FragmentPhase = FragmentPhase.EMPTY
    text: str = ""
    created_mono: float = 0.0
    source_utterance_id: str = ""
    timer_id: str | None = None

    def clear(self) -> None:
        self.phase = FragmentPhase.EMPTY
        self.text = ""
        self.created_mono = 0.0
        self.source_utterance_id = ""
        self.timer_id = None

    def hold(self, text: str, *, utterance_id: str, mono: float) -> None:
        self.phase = FragmentPhase.HELD
        self.text = text
        self.created_mono = mono
        self.source_utterance_id = utterance_id

    def is_held(self) -> bool:
        return self.phase == FragmentPhase.HELD and bool(self.text)

    def elapsed_ms(self, now_mono: float) -> float:
        if not self.is_held():
            return 0.0
        return max(0.0, (now_mono - self.created_mono) * 1000.0)

    def should_expire(self, now_mono: float) -> bool:
        if not self.is_held():
            return False
        return self.elapsed_ms(now_mono) >= FRAGMENT_HOLD_TIMEOUT_MS

    def expire(self) -> None:
        if self.is_held():
            self.phase = FragmentPhase.EXPIRED
        else:
            self.clear()

    def merge_with(self, continuation: str) -> str:
        merged = f"{self.text} {continuation}".strip()
        self.clear()
        return merged
