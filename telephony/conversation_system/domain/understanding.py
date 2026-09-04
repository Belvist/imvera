"""Immutable domain types for one conversational turn."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Mapping, Sequence, Tuple


class SttReason(str, Enum):
    """Why the transcript may be empty or unreliable."""

    NONE = "none"
    EMPTY = "empty"
    LOW_CONF = "low_conf"
    ECHO = "echo"
    OFF_AGENDA = "off_agenda"
    STT_UNCERTAIN = "stt_uncertain"


class ConfidenceBand(str, Enum):
    """STT confidence bucket for policy (not a safety verdict)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SpeechAct(str, Enum):
    """Deterministic classification of caller intent for this turn."""

    EMPTY = "empty"
    GREETING = "greeting"
    CLOSING = "closing"
    CLOSING_DIRECT = "closing_direct"
    REFUSAL = "refusal"
    QUESTION = "question"
    META_CONFUSION = "meta_confusion"
    REPAIR = "repair"
    NARRATIVE = "narrative"
    SYMPTOM = "symptom"
    HELP = "help"
    WORRY = "worry"
    AFFIRMATION = "affirmation"
    ACK = "ack"
    CONTENT = "content"


class ResponseGoalKind(str, Enum):
    """Typed reply objective — composer/FSM consume this, not free text."""

    ACKNOWLEDGE = "acknowledge"
    ASK_TOPIC = "ask_topic"
    CLARIFY = "clarify"
    ANSWER_SIDE = "answer_side"
    SYMPTOM_FOLLOWUP = "symptom_followup"
    SAFETY_CONFIRM = "safety_confirm"
    SAFETY_ACTIVE = "safety_active"
    HELP_OFFER = "help_offer"
    WRAP_UP = "wrap_up"
    CLOSE = "close"
    GREET = "greet"
    REPAIR = "repair"


class AgendaCommand(str, Enum):
    """Explicit agenda mutations requested by policy layer."""

    NONE = "none"
    ADVANCE = "advance"
    DEFER = "defer"
    PAUSE = "pause"
    RESUME = "resume"
    MARK_DISCUSSED = "mark_discussed"


class SafetyCommand(str, Enum):
    """Bridge commands toward SafetyEngine / safety FSM (phase 2)."""

    NONE = "none"
    OBSERVE = "observe"
    CONFIRM = "confirm"
    ESCALATE = "escalate"
    CLEAR = "clear"


@dataclass(frozen=True)
class ResponseGoal:
    """What kind of reply the composer should produce."""

    kind: ResponseGoalKind
    topic: str = ""
    symptom_focus: str = ""
    allow_llm: bool = False
    scripted_only: bool = False
    must_do: str = ""
    forbidden: str = ""
    next_topic: str = ""


@dataclass(frozen=True)
class PolicyDecision:
    """Resolver output: goal + side effects, no spoken text."""

    primary_goal: ResponseGoal
    agenda_command: AgendaCommand = AgendaCommand.NONE
    safety_command: SafetyCommand = SafetyCommand.NONE
    allow_llm: bool = False
    record_notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryPatch:
    """Explicit extended-state mutation — guards stay pure."""

    set_field: Mapping[str, Any] = field(default_factory=dict)
    add_fact: str = ""
    mark_topic_discussed: str = ""
    increment_empty_turns: int = 0
    reset_empty_turns: bool = False
    append_note: str = ""
    family_answer: Tuple[str, str] = ()  # (question_id, answer_text)


@dataclass
class FamilyQuestion:
    """Snapshot of a pending family-app question for this call."""

    id: str
    text: str
    author: str = "Родные"
    status: Literal["pending", "asked", "answered", "expired"] = "pending"
    answer: str | None = None


@dataclass(frozen=True)
class TurnUnderstanding:
    """Immutable parse of one caller turn — built once per turn."""

    raw_text: str
    clean_text: str
    input_reason: SttReason
    speech_act: SpeechAct
    topic_signals: Tuple[str, ...]
    symptom_focus: str | None
    answers_last_control: bool | None
    confidence_band: ConfidenceBand
    is_narrative: bool
    word_count: int
    safety_event_kind: str = ""
    mentions_symptom: bool = False
    symptom_resolved: bool = False
    matches_current_topic: bool = False

    @property
    def has_content(self) -> bool:
        return bool(self.clean_text) and self.speech_act not in (
            SpeechAct.EMPTY,
        )
