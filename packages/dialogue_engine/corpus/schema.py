"""Corpus scenario schema — steps + expectations for full FSM trajectories."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

WellnessCategory = Literal["good", "normal", "so_so", "okay", "bad"]

FAMILY_NAMES: tuple[str, ...] = (
    "clean_short",
    "clean_long",
    "colloquial",
    "paraphrase",
    "contextual",
    "self_correction",
    "repair_allo",
    "repair_repeat",
    "repair_what",
    "backchannel",
    "off_topic_once",
    "unclear_once",
    "silence_once",
    "delayed_answer",
    "interrupted_question",
    "stale_speak",
    "stale_timer",
    "duplicate_playout",
    "long_processing",
    "full_mixed",
)

VARIANTS_PER_FAMILY = 5
SCENARIOS_PER_CATEGORY = len(FAMILY_NAMES) * VARIANTS_PER_FAMILY


@dataclass(frozen=True)
class SlotAnswers:
    wellness: str
    mood: str
    sleep: str
    plans: str
    goodbye: str = "до свидания"
    confirm: str = "да"


@dataclass(frozen=True)
class UserStep:
    text: str
    delayed: bool = False


@dataclass(frozen=True)
class DeliverPlayout:
    """Mark last pending question speak as delivered (PlayoutCompleted)."""

    include_summary: bool = False


@dataclass(frozen=True)
class DeliverPlayoutDuplicate:
    """Fire PlayoutCompleted twice for the same generation — idempotent check."""


@dataclass(frozen=True)
class FireTimerExpired:
    timer_id: str = ""


@dataclass(frozen=True)
class DeferLastSpeak:
    """Simulate CallActor deferring delivery while STT is in flight."""


@dataclass(frozen=True)
class StaleLastSpeak:
    """Simulate stale SpeakEffect after revision bump — engine may re-emit."""


@dataclass(frozen=True)
class ExpectSlot:
    slot: str
    filled: bool = True


@dataclass(frozen=True)
class ExpectSpeakIntent:
    intent: str


@dataclass(frozen=True)
class ExpectTerminal:
    intent: str = "goodbye_final"


CorpusStep = (
    UserStep
    | DeliverPlayout
    | DeliverPlayoutDuplicate
    | FireTimerExpired
    | DeferLastSpeak
    | StaleLastSpeak
    | ExpectSlot
    | ExpectSpeakIntent
    | ExpectTerminal
)


@dataclass(frozen=True)
class FullDialogueScenario:
    id: str
    wellness_category: WellnessCategory
    family: str
    variant: int
    answers: SlotAnswers
    steps: tuple[CorpusStep, ...]
    allow_partial_close: bool = False
    expected_wellness_ack_prefix: str = "Хорошо."


@dataclass
class CorpusInvariantReport:
    opening_replays: int = 0
    planner_legacy_events: int = 0
    stale_state_mutations: int = 0
    duplicate_playout_mutations: int = 0
    undelivered_question_answers: int = 0
    premature_unresolved_close: int = 0
    lost_speak_effects: int = 0
    failed_to_goodbye_final: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "opening_replays": self.opening_replays,
            "planner_legacy_events": self.planner_legacy_events,
            "stale_state_mutations": self.stale_state_mutations,
            "duplicate_playout_mutations": self.duplicate_playout_mutations,
            "undelivered_question_answers": self.undelivered_question_answers,
            "premature_unresolved_close": self.premature_unresolved_close,
            "lost_speak_effects": self.lost_speak_effects,
            "failed_to_goodbye_final": self.failed_to_goodbye_final,
        }
