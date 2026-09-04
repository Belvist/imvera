"""ConversationState contract — fields the Observer maintains per call."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple

from conversation_system.domain.pending_question import PendingQuestion


class FactStatus(str, Enum):
    """Lifecycle of a remembered fact."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    CONTRADICTED = "contradicted"


@dataclass
class ConversationFact:
    """One fact with explicit status for contradiction tracking."""

    text: str
    status: FactStatus = FactStatus.ACTIVE
    source_turn: int = 0


@dataclass
class ConversationState:
    """
    Observer-owned projection of conversational state.

    Mirrors and extends ``ConversationMemory`` with structured facts,
    unanswered user questions, and the next directive for the main agent.
    """

    facts: List[ConversationFact] = field(default_factory=list)
    pending_question: PendingQuestion | None = None
    unanswered_user_questions: List[str] = field(default_factory=list)
    corrections: List[str] = field(default_factory=list)
    answered_user_questions: List[str] = field(default_factory=list)
    next_directive: str = ""

    def active_facts(self) -> Tuple[str, ...]:
        return tuple(
            f.text for f in self.facts
            if f.status == FactStatus.ACTIVE and f.text.strip()
        )

    def add_fact(self, text: str, *, turn_no: int = 0) -> None:
        t = (text or "").strip()
        if not t:
            return
        for f in self.facts:
            if f.text == t and f.status == FactStatus.ACTIVE:
                return
        self.facts.append(ConversationFact(text=t, source_turn=turn_no))
        if len(self.facts) > 16:
            self.facts = self.facts[-16:]

    def mark_contradicted(self, substring: str) -> None:
        sub = (substring or "").strip().lower()
        if not sub:
            return
        for f in self.facts:
            if sub in f.text.lower():
                f.status = FactStatus.CONTRADICTED

    def mark_question_answered(self, question: str) -> None:
        q = (question or "").strip()
        if not q:
            return
        if q not in self.answered_user_questions:
            self.answered_user_questions.append(q)
        self.unanswered_user_questions = [
            u for u in self.unanswered_user_questions if u.strip() != q
        ]
