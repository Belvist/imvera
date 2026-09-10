"""DialogueEngine state — sole conversational truth for pilot daily-check flow."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from packages.contracts.enums import FsmState, SlotStatus
from packages.contracts.semantic import IssueMention
from packages.dialogue_engine.context import SlotValue
from packages.dialogue_engine.effects import SpeakEffect


class CheckPath(StrEnum):
    STANDARD = "standard"
    NEGATIVE_PROBE = "negative_probe"
    PAIN_SHORT = "pain_short"
    URGENT = "urgent"


class BackgroundGoalCoverage(StrEnum):
    UNSEEN = "unseen"
    COVERED_FROM_SPEECH = "covered_from_speech"
    ASKED = "asked"
    ANSWERED = "answered"
    SKIPPED = "skipped"


_BACKGROUND_SLOTS = ("wellness", "mood", "sleep", "plans")

MAX_SLOT_ATTEMPTS = 2


class OpeningState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PLAYING = "PLAYING"
    DELIVERED = "DELIVERED"


class QuestionPhase(StrEnum):
    PLANNED = "PLANNED"
    SYNTHESIZING = "SYNTHESIZING"
    PLAYING = "PLAYING"
    DELIVERED = "DELIVERED"
    ANSWERED = "ANSWERED"
    CANCELLED = "CANCELLED"


class Question(BaseModel):
    question_id: str
    slot: str
    text: str
    phase: QuestionPhase = QuestionPhase.PLANNED
    intent: str = ""

    model_config = {"frozen": True}


class GoalState(BaseModel):
    slot: str
    delivered_attempts: int = 0
    max_attempts: int = MAX_SLOT_ATTEMPTS
    status: SlotStatus = SlotStatus.OPEN
    reserved_question_id: str | None = None

    model_config = {"frozen": False}


class TopicEvidence(BaseModel):
    """Family-specific clause plus full turn for cross-clause temporal context."""

    clause: str
    turn_text: str

    model_config = {"frozen": True}


class TopicResolution(StrEnum):
    OPEN = "open"
    IMPROVING = "improving"
    RESOLVED = "resolved"


class IssueEpisode(BaseModel):
    episode_id: str
    primary_label: str
    kind: str
    body_site: str | None = None

    mentions: list[IssueMention] = Field(default_factory=list)
    evidence_turn_ids: list[str] = Field(default_factory=list)

    known_attributes: dict[str, str] = Field(default_factory=dict)

    status: Literal["open", "suspended", "resolved"] = "open"

    model_config = {"frozen": False}


class SuspendedObligation(BaseModel):
    kind: str
    episode_id: str | None = None
    attribute: str | None = None
    slot: str | None = None
    intent: str | None = None

    model_config = {"frozen": True}


class EngineState(BaseModel):
    call_id: str
    elder_display_name: str = "Анной Петровной"
    revision: int = 0

    fsm_state: FsmState = FsmState.CALL_START
    opening_state: OpeningState = OpeningState.NOT_STARTED
    opening_play_count: int = 0
    first_user_turn_received: bool = False

    slots: dict[str, SlotStatus] = Field(
        default_factory=lambda: {
            "wellness": SlotStatus.OPEN,
            "mood": SlotStatus.OPEN,
            "sleep": SlotStatus.OPEN,
            "plans": SlotStatus.OPEN,
        }
    )
    slot_values: dict[str, str] = Field(default_factory=dict)
    slot_records: dict[str, SlotValue] = Field(default_factory=dict)
    goals: dict[str, GoalState] = Field(default_factory=dict)

    planned_question: Question | None = None
    playing_question: Question | None = None
    delivered_question: Question | None = None
    active_playout: Question | None = None

    processing_turn_id: str | None = None
    processing_effect_id: str | None = None
    active_playout_generation: int = 0

    slot_unclear_counts: dict[str, int] = Field(default_factory=dict)
    waiting_on_slot: str | None = None
    summary_spoken: bool = False
    awaiting_goodbye_confirm: bool = False
    goodbye_confirmed: bool = False
    goodbye_count: int = 0
    call_closed: bool = False
    closing_reason: str | None = None

    turn_seq: int = 0
    generation_seq: int = 0
    deferred_speak: SpeakEffect | None = None
    slot_corrections: list[dict[str, str]] = Field(default_factory=list)

    check_path: CheckPath = CheckPath.STANDARD
    probe_phase: str | None = None
    skipped_slots: set[str] = Field(default_factory=set)
    wellness_concern: str = ""
    wellness_duration: str = ""
    pain_at_night: str = ""
    prior_call_context: dict[str, str] = Field(default_factory=dict)
    follow_up_opening: bool = False
    wellness_probes_enabled: bool = True

    active_topic: str | None = None
    pending_topics: list[str] = Field(default_factory=list)
    topic_dimensions: dict[str, list[str]] = Field(default_factory=dict)
    topic_evidence: dict[str, list[TopicEvidence]] = Field(default_factory=dict)
    topic_resolution: dict[str, str] = Field(default_factory=dict)
    topic_asked_dimension: str | None = None

    active_episode_id: str | None = None
    pending_episode_ids: list[str] = Field(default_factory=list)
    issue_episodes: dict[str, IssueEpisode] = Field(default_factory=dict)
    suspended_obligation: SuspendedObligation | None = None
    pending_episode_attribute: str | None = None

    observations: dict[str, object] = Field(default_factory=dict)

    background_goal_status: dict[str, str] = Field(
        default_factory=lambda: {
            "wellness": BackgroundGoalCoverage.UNSEEN,
            "mood": BackgroundGoalCoverage.UNSEEN,
            "sleep": BackgroundGoalCoverage.UNSEEN,
            "plans": BackgroundGoalCoverage.UNSEEN,
        }
    )
    important_to_share_asked: bool = False
    important_to_share_resolved: bool = False

    # Background goals are optional unless explicitly required (UNSEEN ≠ MUST ASK).
    required_background_goals: set[str] = Field(default_factory=set)
    mandatory_background_goals: bool = False

    # Ephemeral shadow telemetry — never persisted via model dump / DB snapshot.
    action_policy_shadow_records: list[dict] = Field(
        default_factory=list,
        exclude=True,
        repr=False,
    )
    action_policy_shadow_health: dict = Field(
        default_factory=dict,
        exclude=True,
        repr=False,
    )
    action_policy_shadow_decision_ordinal: int = Field(
        default=0,
        exclude=True,
        repr=False,
    )

    def uses_issue_episodes(self) -> bool:
        return bool(self.issue_episodes or self.active_episode_id)

    def bump_revision(self) -> None:
        self.revision += 1

    def next_generation_id(self) -> str:
        self.generation_seq += 1
        return f"g-{self.generation_seq}"

    def ensure_goal(self, slot: str) -> GoalState:
        goal = self.goals.get(slot)
        if goal is None:
            goal = GoalState(slot=slot)
            self.goals[slot] = goal
        return goal

    def answer_context_slot(self) -> str | None:
        """Slot used to interpret the next user answer — delivered, not planned."""
        if self.probe_phase:
            return f"probe_{self.probe_phase}"
        if self.delivered_question is not None:
            return self.delivered_question.slot
        if self.playing_question is not None:
            return self.playing_question.slot
        return None

    def next_open_slot(self) -> str | None:
        """Compatibility helper — scheduler owns next-turn decisions."""
        if self.check_path == CheckPath.URGENT:
            return None
        for slot in _BACKGROUND_SLOTS:
            if slot in self.skipped_slots:
                continue
            if self.slots.get(slot) == SlotStatus.OPEN:
                return slot
        return None

    def set_background_goal_coverage(self, slot: str, coverage: BackgroundGoalCoverage) -> None:
        if slot in self.background_goal_status:
            self.background_goal_status[slot] = coverage.value

    def background_goal_needs_attention(self, slot: str) -> bool:
        if slot in self.skipped_slots:
            return False
        if self.slots.get(slot) != SlotStatus.OPEN:
            return False
        status = self.background_goal_status.get(slot, BackgroundGoalCoverage.UNSEEN)
        if status == BackgroundGoalCoverage.ASKED:
            return True
        if status != BackgroundGoalCoverage.UNSEEN:
            return False
        if self.mandatory_background_goals:
            return True
        return slot in self.required_background_goals
