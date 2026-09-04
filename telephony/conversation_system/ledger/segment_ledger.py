"""Segment lifecycle ledger — GENERATED → PLAYING → PLAYED / CANCELLED."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class SegmentStatus(str, Enum):
    GENERATED = "generated"
    PLAYING = "playing"
    PLAYED = "played"
    CANCELLED = "cancelled"


@dataclass
class SegmentRecord:
    """One TTS segment tied to a question generation."""

    id: str
    generation_id: int
    question_id: str = ""
    slot: str = ""
    status: SegmentStatus = SegmentStatus.GENERATED
    segment_path: str = ""


@dataclass
class SegmentLedger:
    """Per-call segment playback lifecycle."""

    records: List[SegmentRecord] = field(default_factory=list)
    _by_id: Dict[str, SegmentRecord] = field(default_factory=dict, repr=False)

    def _new_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def register_generated(
        self,
        *,
        generation_id: int,
        question_id: str = "",
        slot: str = "",
        segment_path: str = "",
    ) -> SegmentRecord:
        rec = SegmentRecord(
            id=self._new_id(),
            generation_id=generation_id,
            question_id=(question_id or "").strip(),
            slot=(slot or "").strip(),
            status=SegmentStatus.GENERATED,
            segment_path=(segment_path or "").strip(),
        )
        self.records.append(rec)
        self._by_id[rec.id] = rec
        return rec

    def mark_playing(self, segment_id: str) -> Optional[SegmentRecord]:
        rec = self._by_id.get(segment_id)
        if rec is None or rec.status != SegmentStatus.GENERATED:
            return None
        rec.status = SegmentStatus.PLAYING
        return rec

    def mark_played(self, segment_id: str) -> Optional[SegmentRecord]:
        rec = self._by_id.get(segment_id)
        if rec is None:
            for candidate in reversed(self.records):
                if candidate.segment_path and candidate.segment_path.endswith(segment_id):
                    rec = candidate
                    break
        if rec is None:
            return None
        if rec.status in (SegmentStatus.PLAYED, SegmentStatus.CANCELLED):
            return rec
        rec.status = SegmentStatus.PLAYED
        return rec

    def mark_cancelled(self, *, generation_id: int | None = None) -> int:
        count = 0
        for rec in self.records:
            if generation_id is not None and rec.generation_id != generation_id:
                continue
            if rec.status in (SegmentStatus.GENERATED, SegmentStatus.PLAYING):
                rec.status = SegmentStatus.CANCELLED
                count += 1
        return count

    def last_for_generation(self, generation_id: int) -> Optional[SegmentRecord]:
        for rec in reversed(self.records):
            if rec.generation_id == generation_id:
                return rec
        return None
