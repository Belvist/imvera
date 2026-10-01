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


class GoalLifecycle(StrEnum):
    """Runtime lifecycle for mission / slot goals (distinct from GoalDefinition)."""

    UNSEEN = "UNSEEN"
    AVAILABLE = "AVAILABLE"
    ACTIVE = "ACTIVE"
    ASKED = "ASKED"
    ANSWER_PENDING = "ANSWER_PENDING"
    SATISFIED = "SATISFIED"
    DECLINED = "DECLINED"
    SKIPPED = "SKIPPED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BLOCKED = "BLOCKED"
    UNCLEAR = "UNCLEAR"


class Question(BaseModel):
    question_id: str
    slot: str
    text: str
    phase: QuestionPhase = QuestionPhase.PLANNED
    intent: str = ""
    goal_id: str | None = None

    model_config = {"frozen": True}


class GoalState(BaseModel):
    """Runtime goal progress. Catalog fields live on GoalDefinition (mission)."""

    slot: str  # compatibility key; for mission goals equals goal_id
    goal_id: str = ""
    delivered_attempts: int = 0
    max_attempts: int = MAX_SLOT_ATTEMPTS
    status: SlotStatus = SlotStatus.OPEN  # legacy slot projection
    lifecycle: GoalLifecycle = GoalLifecycle.AVAILABLE
    reserved_question_id: str | None = None
    answer: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    source: str = "slot"

    model_config = {"frozen": False}

    def resolved_goal_id(self) -> str:
        return self.goal_id or self.slot


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
    # Whose complaint (SubjectKind value): speaker | other_person | unknown.
    # Single source of truth — no parallel notations. unknown is preserved
    # (never defaulted to speaker); merge never downgrades a known subject.
    subject: str = "unknown"
    canonical_key: str = ""

    mentions: list[IssueMention] = Field(default_factory=list)
    evidence_turn_ids: list[str] = Field(default_factory=list)

    known_attributes: dict[str, str] = Field(default_factory=dict)
    # Unanswered questions are evidence of missing information, never facts
    # about the symptom. Keep the caller's own quote for honest reporting.
    unanswered_attributes: dict[str, str] = Field(default_factory=dict)

    status: Literal["open", "suspended", "resolved"] = "open"

    model_config = {"frozen": False}


class SuspendedObligation(BaseModel):
    kind: str
    episode_id: str | None = None
    attribute: str | None = None
    slot: str | None = None
    intent: str | None = None
    goal_id: str | None = None
    reason: str | None = None
    resume_policy: str | None = None

    model_config = {"frozen": True}


class EngineState(BaseModel):
    call_id: str
    elder_display_name: str = "Анной Петровной"
    # Stable client key for per-client phrase memory (caller number / elder
    # id from telephony). "" = unknown → memory disabled (call-scoped).
    client_id: str = ""
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
    # Immutable mission input snapshot (definitions only). Runtime = goals.
    mission_id: str = "daily_check"
    mission_preset: str | None = "daily_check"
    mission_goal_ids: tuple[str, ...] = ()
    # GoalDefinition catalog from CallMission — not a second runtime store.
    mission_catalog: tuple = ()

    planned_question: Question | None = None
    playing_question: Question | None = None
    delivered_question: Question | None = None
    active_playout: Question | None = None

    processing_turn_id: str | None = None
    processing_effect_id: str | None = None
    active_playout_generation: int = 0

    slot_unclear_counts: dict[str, int] = Field(default_factory=dict)
    last_temporal_probe: Literal["temporal_onset", "temporal_duration"] | None = None
    waiting_on_slot: str | None = None
    summary_spoken: bool = False
    summary_delivered: bool = False
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

    # Dialogue Product Pack counters (caps: ≤2 asks/family, ≤6 content asks/call).
    product_asks_by_family: dict[str, int] = Field(default_factory=dict)
    product_content_asks: int = 0

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
    # Frozen MEDICATION followup asked once per call (pack status_today).
    medication_asked: bool = False
    # Reluctance: client signals they are done (short answers, irritation,
    # explicit finish). >=3 → warm early close instead of squeezing.
    reluctance_score: int = 0
    # Coverage filler domains already asked once (never re-ask declined).
    coverage_asked_domains: set[str] = Field(default_factory=set)
    # Baseline filler awaiting an answer (medication/nutrition/mood/sleep).
    pending_coverage_domain: str | None = None
    # Coverage domains already re-asked once after debris (no third ask).
    coverage_reasked_domains: set[str] = Field(default_factory=set)
    # Asked-question history (spoken question texts, cap 20) — answers
    # «а что ты спрашивал?» and never-repeat audits. Not state for logic.
    asked_history: list[str] = Field(default_factory=list)
    # Asked-question signatures (normalized, ring cap 8) — the single
    # repeat check. Written at the same emit funnel as asked_history;
    # the rephrase picker reads this ring, never its own copy.
    asked_signatures: list[str] = Field(default_factory=list)
    # Discourse: what the person is talking about now. Written by
    # update_discourse from verified semantics only (mentions, grounded
    # facts, their question) — never from free text. Read by the
    # FOLLOW_USER_THREAD branch; decays after 3 uncontinued turns.
    current_thread_label: str = ""
    current_thread_turns: int = 0
    # Verbatim span worth one follow-up («внучка приезжала»). Set only
    # from a substantive turn's own words, consumed once, never from
    # garbage or silence.
    open_hook: str = ""
    open_hook_used: bool = False
    # Normalized signature of what Vera just acknowledged — anti-parrot
    # for acks (questions are covered by asked_signatures).
    last_ack_signature: str = ""
    # Speech ledger: normalized surfaces of everything Vera already said
    # this call (cap 60). Recorded at the single emit funnel for repeat
    # audits and the speech-discipline gate; repair repeats bypass nothing
    # here since the ledger never diverts.
    spoken_surfaces: list[str] = Field(default_factory=list)
    # Consecutive backchannel-only turns («ага» × N). Three in a row with
    # no engagement closes honestly — independent of per-slot attempt caps,
    # which rotation across slots would otherwise dilute.
    backchannel_streak: int = 0
    # Per-pool rotation counters for rotate_pool (pool key -> next index).
    # Seeded by day on first use, so single asks are byte-identical to
    # day rotation and only true repeats advance to the next variant.
    pool_counters: dict[str, int] = Field(default_factory=dict)
    # CDK Step 2: act-driven NeedQueue. forbidden_actions blocks probes a
    # DECLINE ruled out (per-call; lifted only by restated complaint).
    # queued_needs holds must-ask items (e.g. severity) served before ITS.
    forbidden_actions: list[str] = Field(default_factory=list)
    queued_needs: list[str] = Field(default_factory=list)
    # CDK Step 3: last normalized act ("" when none). Read-only signal for
    # downstream guards; routing never assigns meaning to free text here.
    last_protocol_act: str = ""
    # Elder asked to stop being probed («не беспокой меня»). Silences the
    # routine question ladders only — safety/grounding still win.
    elder_asked_to_stop: bool = False
    # Wellness clarify asked once after a mute/garbled first answer.
    wellness_clarify_asked: bool = False
    # Silence reprompts used (max 1 per call): a 7 s silence is not an answer
    # attempt — the first timeout re-asks («Алло. …») without consuming caps,
    # only the second one may close (live fs-51d62138 gave up at first silence).
    silence_reprompts: int = 0
    # Volunteered-topic ack spoken once per call («Хорошо, что поели» before
    # moving on — volunteered food/sleep must be acknowledged, not skipped).
    volunteered_ack_done: bool = False
    # Mic-check spoken once per call (uplink dead: zero PCM frames received —
    # say «Вас не слышно», not the question again and not goodbye).
    mic_check_spoken: bool = False
    # Red state («умираю» without a site): concern still being clarified —
    # escalate after the second vague answer even with nothing concrete.
    red_state_pending: bool = False
    # Concern probes asked on negative wellness without complaint.
    concern_probe_count: int = 0
    # Proposed by scheduler; committed only after PlayoutCompleted.
    important_to_share_planned: bool = False
    pending_resume_goal_id: str | None = None
    pending_episode_attribute_planned: str | None = None

    # Conversational safety / target presence (engine-owned when DialogueEngine active).
    safety_mode: str = "none"  # none | yellow | red
    safety_clarify_count: int = 0
    risk_handling: bool = False
    risk_episode_id: str | None = None
    target_presence: str = "unknown"  # unknown | confirmed | third_party | unavailable
    target_display_name: str = ""

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
    action_policy_router_stats: dict = Field(
        default_factory=dict,
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
            goal = GoalState(slot=slot, goal_id=slot)
            self.goals[slot] = goal
        elif not goal.goal_id:
            goal.goal_id = slot
        return goal

    def mission_goal(self, goal_id: str) -> GoalState | None:
        return self.goals.get(goal_id)

    def unanswered_required_mission_goals(self) -> list[GoalState]:
        out: list[GoalState] = []
        for gid in self.mission_goal_ids:
            goal = self.goals.get(gid)
            if goal is None:
                continue
            if goal.lifecycle in {
                GoalLifecycle.SATISFIED,
                GoalLifecycle.DECLINED,
                GoalLifecycle.SKIPPED,
                GoalLifecycle.NOT_APPLICABLE,
            }:
                continue
            out.append(goal)
        return out

    def answer_context_slot(self) -> str | None:
        """Slot/goal used to interpret the next user answer — delivered, not planned."""
        if self.probe_phase:
            return f"probe_{self.probe_phase}"
        if self.delivered_question is not None:
            return self.delivered_question.goal_id or self.delivered_question.slot
        if self.playing_question is not None:
            return self.playing_question.goal_id or self.playing_question.slot
        # Custom mission: fall back to ACTIVE/ASKED/ANSWER_PENDING goal.
        for gid in self.mission_goal_ids:
            goal = self.goals.get(gid)
            if goal and goal.lifecycle in {
                GoalLifecycle.ACTIVE,
                GoalLifecycle.ASKED,
                GoalLifecycle.ANSWER_PENDING,
            }:
                return goal.resolved_goal_id()
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
