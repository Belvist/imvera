"""QuestionLedger — slot-scoped question lifecycle (Phase 6).

Tracks PLANNED → ASKED → HEARD → ANSWERED with barge-in CANCELLED.
Prevents re-asking ANSWERED slots unless RECONFIRM_REQUIRED.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple


class QuestionStatus(str, Enum):
    PLANNED = "planned"
    GENERATED = "generated"
    PLAYING = "playing"
    PLAYED = "played"
    ASKED = "asked"
    HEARD = "heard"
    ANSWERED = "answered"
    SKIPPED = "skipped"
    DECLINED = "declined"
    RECONFIRM_REQUIRED = "reconfirm_required"
    CANCELLED = "cancelled"


_TERMINAL = frozenset({
    QuestionStatus.ANSWERED,
    QuestionStatus.SKIPPED,
    QuestionStatus.DECLINED,
    QuestionStatus.CANCELLED,
})


@dataclass
class QuestionRecord:
    """One agenda or probe question instance."""

    id: str
    slot: str
    question_id: str = ""
    status: QuestionStatus = QuestionStatus.PLANNED
    asked_turn: int = 0
    heard_turn: int = 0
    answered_turn: int = 0
    asked_text: str = ""
    answer: str = ""
    generation_id: int = 0
    segment_id: str = ""


@dataclass
class QuestionLedger:
    """Per-call ledger of asked/heard/answered questions by semantic slot."""

    records: List[QuestionRecord] = field(default_factory=list)
    _by_id: Dict[str, QuestionRecord] = field(default_factory=dict, repr=False)
    _active_ask_id: str = ""

    def _new_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def slot_status(self, slot: str) -> QuestionStatus | None:
        s = (slot or "").strip()
        if not s:
            return None
        for rec in reversed(self.records):
            if rec.slot == s:
                return rec.status
        return None

    def can_ask_slot(self, slot: str) -> bool:
        """False when slot was answered and does not need reconfirm."""
        s = (slot or "").strip()
        if not s:
            return True
        status = self.slot_status(s)
        if status is None:
            return True
        if status == QuestionStatus.RECONFIRM_REQUIRED:
            return True
        if status in _TERMINAL:
            return status != QuestionStatus.ANSWERED
        return True

    def forbidden_slots(self) -> Tuple[str, ...]:
        return tuple(
            rec.slot
            for rec in self.records
            if rec.status == QuestionStatus.ANSWERED and rec.slot
        )

    def plan_slot(self, slot: str, *, turn: int = 0) -> QuestionRecord:
        s = (slot or "").strip()
        if not s:
            raise ValueError("plan_slot requires non-empty slot")
        if not self.can_ask_slot(s):
            raise ValueError(f"slot {s!r} already answered")
        qid = self._new_id()
        rec = QuestionRecord(id=qid, question_id=qid, slot=s, asked_turn=turn)
        self.records.append(rec)
        self._by_id[rec.id] = rec
        return rec

    def mark_generated(self, question_id: str, *, segment_id: str = "") -> None:
        rec = self._by_id.get(question_id)
        if rec is None:
            return
        rec.status = QuestionStatus.GENERATED
        if segment_id:
            rec.segment_id = segment_id

    def mark_playing(self, question_id: str) -> None:
        rec = self._by_id.get(question_id)
        if rec is None or rec.status not in (
                QuestionStatus.ASKED,
                QuestionStatus.GENERATED,
        ):
            return
        rec.status = QuestionStatus.PLAYING

    def mark_played(self, question_id: str) -> None:
        rec = self._by_id.get(question_id)
        if rec is None or rec.status == QuestionStatus.CANCELLED:
            return
        rec.status = QuestionStatus.PLAYED

    def mark_asked(
        self,
        question_id: str,
        *,
        text: str,
        turn: int,
        generation_id: int = 0,
        segment_id: str = "",
    ) -> None:
        rec = self._by_id.get(question_id)
        if rec is None:
            return
        rec.status = QuestionStatus.ASKED
        rec.asked_text = (text or "").strip()
        rec.asked_turn = turn
        rec.generation_id = generation_id
        rec.segment_id = segment_id or rec.segment_id
        self._active_ask_id = question_id

    def mark_heard(self, question_id: str, *, turn: int) -> None:
        rec = self._by_id.get(question_id)
        if rec is None:
            return
        if rec.status not in (
                QuestionStatus.ASKED,
                QuestionStatus.PLAYING,
                QuestionStatus.PLAYED,
        ):
            return
        rec.status = QuestionStatus.HEARD
        rec.heard_turn = turn

    def record_by_id(self, question_id: str) -> QuestionRecord | None:
        return self._by_id.get(question_id)

    def mark_answered(
        self,
        slot: str,
        *,
        answer: str,
        turn: int,
        question_id: str = "",
    ) -> None:
        s = (slot or "").strip()
        if not s:
            return
        rec: QuestionRecord | None = None
        if question_id:
            rec = self._by_id.get(question_id)
        if rec is None:
            for candidate in reversed(self.records):
                if candidate.slot == s and candidate.status in (
                        QuestionStatus.ASKED,
                        QuestionStatus.HEARD,
                        QuestionStatus.PLANNED,
                ):
                    rec = candidate
                    break
        if rec is None:
            rec = self.plan_slot(s, turn=turn)
        rec.status = QuestionStatus.ANSWERED
        rec.answer = (answer or "").strip()
        rec.answered_turn = turn
        if self._active_ask_id == rec.id:
            self._active_ask_id = ""

    def mark_cancelled(
        self,
        *,
        generation_id: int | None = None,
        question_id: str = "",
    ) -> None:
        """Barge-in before caller heard the question."""
        targets: Sequence[QuestionRecord]
        if question_id:
            rec = self._by_id.get(question_id)
            targets = (rec,) if rec else ()
        elif generation_id is not None:
            targets = tuple(
                r for r in self.records
                if r.generation_id == generation_id
                and r.status == QuestionStatus.ASKED
            )
        else:
            rec = self._by_id.get(self._active_ask_id)
            targets = (rec,) if rec else ()
        for rec in targets:
            if rec is None:
                continue
            if rec.status == QuestionStatus.ASKED:
                rec.status = QuestionStatus.CANCELLED
        if question_id and self._active_ask_id == question_id:
            self._active_ask_id = ""

    def require_reconfirm(self, slot: str) -> None:
        s = (slot or "").strip()
        if not s:
            return
        for rec in reversed(self.records):
            if rec.slot == s and rec.status == QuestionStatus.ANSWERED:
                rec.status = QuestionStatus.RECONFIRM_REQUIRED
                return

    def active_question_id(self) -> str:
        return self._active_ask_id

    def record_for_slot(self, slot: str) -> Optional[QuestionRecord]:
        s = (slot or "").strip()
        for rec in reversed(self.records):
            if rec.slot == s:
                return rec
        return None
