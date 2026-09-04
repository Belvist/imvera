"""Public API types — ConversationFacade contract."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class SessionHandle:
    """Opaque session reference for orchestrator."""

    call_id: str
    internal_id: str


@dataclass
class TurnPlanV2:
    """Single-turn plan — no intent/fallback fork."""

    user_text: str
    spoken_reply: str
    stream: bool
    terminal: bool
    verdict: str
    safety_status: str
    record_notes: List[str] = field(default_factory=list)
    dialogue_step: int = 0
    greeting: str | None = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnCommit:
    """Result of committing one turn."""

    spoken_text: str
    memory_patches_applied: int
    phase: str
    agenda_cursor: int
    topics_discussed: List[str] = field(default_factory=list)


@dataclass
class CallSummary:
    """End-of-call export."""

    verdict: str
    notes: List[str]
    family_questions: List[dict]
    duration_turns: int
    consent_outcome: str | None = None


class SessionNotFound(LookupError):
    """Raised when handle is unknown — fail closed."""


class TurnPipelineError(RuntimeError):
    """Unrecoverable pipeline failure."""
