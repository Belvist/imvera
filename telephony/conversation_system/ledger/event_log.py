"""Append-only conversation event log (Phase 6)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping


class ConversationEventType(str, Enum):
    TURN_PLANNED = "turn_planned"
    TURN_COMMITTED = "turn_committed"
    QUESTION_ASKED = "question_asked"
    QUESTION_HEARD = "question_heard"
    QUESTION_ANSWERED = "question_answered"
    QUESTION_CANCELLED = "question_cancelled"
    SEGMENT_PLAYED = "segment_played"
    BARGE_IN = "barge_in"
    SAFETY = "safety"
    FACT_ADDED = "fact_added"
    FACT_SUPERSEDED = "fact_superseded"


@dataclass(frozen=True)
class ConversationEvent:
    type: ConversationEventType
    turn: int = 0
    payload: Mapping[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


@dataclass
class EventLog:
    """Append-only log; reducer can sync to ConversationMemory."""

    events: List[ConversationEvent] = field(default_factory=list)

    def append(
        self,
        event_type: ConversationEventType,
        *,
        turn: int = 0,
        **payload: Any,
    ) -> ConversationEvent:
        ev = ConversationEvent(
            type=event_type,
            turn=turn,
            payload=dict(payload),
        )
        self.events.append(ev)
        return ev

    def last_of(self, event_type: ConversationEventType) -> ConversationEvent | None:
        for ev in reversed(self.events):
            if ev.type == event_type:
                return ev
        return None
