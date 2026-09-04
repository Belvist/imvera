"""Extended conversational state — structured, not boolean soup."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Mapping, Sequence

from conversation_system.domain.pending_question import PendingQuestion
from conversation_system.domain.understanding import FamilyQuestion, MemoryPatch


def _default_observer_state():
    from conversation_system.observer.state_contract import ConversationState
    return ConversationState()


@dataclass
class CallFlags:
    """Small set of qualitative flags — not ad-hoc Agent attributes."""

    agenda_paused: bool = False
    agenda_done: bool = False
    help_pending: bool = False
    closing_confirmed: bool = False
    stt_confirm_used: bool = False
    clearing_symptom: bool = False
    hello_back_done: bool = False


@dataclass
class ConversationMemory:
    """Mutable extended state for one call. Mutations via MemoryPatch only."""

    call_id: str = ""
    caller_id: str = ""
    turn_no: int = 0
    facts: List[str] = field(default_factory=list)
    topics_discussed: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    agenda_cursor: int = 0
    agenda_question_open: bool = False
    deferred_topic: str = ""
    wellness_band: str = "unknown"
    empty_turn_count: int = 0
    active_symptom: str = ""
    symptom_resolved: bool = False
    last_question: str = ""
    last_answer: str = ""
    last_reply: str = ""
    last_input_reason: str = ""
    safety_status: str = "unknown"
    family_questions: List[FamilyQuestion] = field(default_factory=list)
    flags: CallFlags = field(default_factory=CallFlags)
    pending_question: PendingQuestion | None = None
    unanswered_user_questions: List[str] = field(default_factory=list)
    answered_user_questions: List[str] = field(default_factory=list)
    corrections: List[str] = field(default_factory=list)
    next_directive: str = ""
    observer_state: object = field(default_factory=_default_observer_state)

    def apply(self, patch: MemoryPatch) -> None:
        """Apply one explicit patch (RTC: caller serializes per-call lock)."""
        for key, value in patch.set_field.items():
            if key == "flags":
                if isinstance(value, Mapping):
                    for fk, fv in value.items():
                        if hasattr(self.flags, fk):
                            setattr(self.flags, fk, fv)
                        elif fk == "agenda_question_open":
                            self.agenda_question_open = bool(fv)
                continue
            if key == "agenda_question_open":
                self.agenda_question_open = bool(value)
                continue
            if hasattr(self, key):
                setattr(self, key, value)

        if patch.add_fact:
            fact = patch.add_fact.strip()
            if fact and fact not in self.facts:
                self.facts.append(fact)
                if len(self.facts) > 12:
                    self.facts = self.facts[-12:]

        if patch.mark_topic_discussed:
            topic = patch.mark_topic_discussed.strip().lower()
            if topic and topic not in self.topics_discussed:
                self.topics_discussed.append(topic)

        if patch.increment_empty_turns:
            self.empty_turn_count += patch.increment_empty_turns

        if patch.reset_empty_turns:
            self.empty_turn_count = 0

        if patch.append_note:
            note = patch.append_note.strip()
            if note:
                self.notes.append(note)

        if patch.family_answer:
            qid, answer = patch.family_answer
            for fq in self.family_questions:
                if fq.id == qid:
                    fq.status = "answered"
                    fq.answer = answer
                    break

    def apply_many(self, patches: Sequence[MemoryPatch]) -> None:
        for p in patches:
            self.apply(p)

    def record_turn(
        self,
        *,
        user_text: str,
        agent_reply: str = "",
        question: str = "",
    ) -> None:
        """Bookkeeping after a committed turn (phase 3+ pipeline)."""
        self.turn_no += 1
        self.last_answer = user_text or ""
        if question:
            self.last_question = question
        if agent_reply:
            self.last_reply = agent_reply

    def mark_question_answered(self, question: str = "") -> None:
        """Remove a side question from the open queue after Vera answered it."""
        q = (question or "").strip()
        if not q and self.unanswered_user_questions:
            q = self.unanswered_user_questions[-1].strip()
        if not q:
            return
        state = self.observer_state
        if hasattr(state, "mark_question_answered"):
            state.mark_question_answered(q)
        self.unanswered_user_questions = [
            u for u in self.unanswered_user_questions if u.strip() != q
        ]
        if q not in self.answered_user_questions:
            self.answered_user_questions.append(q)

    def topics_covered_snapshot(self) -> tuple[str, ...]:
        return tuple(self.topics_discussed)

    def to_skill_context_lines(self) -> list[str]:
        """Read-only projection for future LLM SkillState export."""
        lines: list[str] = []
        if self.deferred_topic:
            lines.append(f"отложенная тема — «{self.deferred_topic}»")
        if self.topics_discussed:
            lines.append("уже обсуждено: " + ", ".join(self.topics_discussed))
        if self.last_question:
            lines.append(f"последний вопрос: {self.last_question}")
        if self.last_reply:
            lines.append(f"ты только что сказала «{self.last_reply}»")
        if self.facts:
            lines.append("факты: " + "; ".join(self.facts))
        if self.active_symptom:
            lines.append(f"активный симптом: {self.active_symptom}")
        return lines

    def clone(self) -> "ConversationMemory":
        import copy
        return copy.deepcopy(self)
