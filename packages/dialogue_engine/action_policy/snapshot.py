"""Immutable, generic policy snapshot built after semantic apply."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.action_policy.needs import ASKABLE_NEEDS
from packages.dialogue_engine.question_context import QuestionNeed
from packages.dialogue_engine.state import BackgroundGoalCoverage, EngineState


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _need_group_known(known: Mapping[str, str], need: str) -> bool:
    if need in ("onset", "duration", "temporal"):
        return bool(known.get("onset") or known.get("duration"))
    if need in ("current", "status"):
        return bool(known.get("current") or known.get("status"))
    return bool(known.get(need))


@dataclass(frozen=True)
class EpisodeSnapshot:
    episode_id: str
    kind: str
    status: str
    known_attributes: tuple[tuple[str, str], ...] = ()
    speaker_owned: bool = True

    @property
    def known(self) -> dict[str, str]:
        return dict(self.known_attributes)

    def need_known(self, need: QuestionNeed | str) -> bool:
        attrs = need.attributes if isinstance(need, QuestionNeed) else (need,)
        return all(_need_group_known(self.known, attr) for attr in attrs)

    @property
    def temporal_known(self) -> bool:
        return _need_group_known(self.known, "temporal")

    @property
    def current_known(self) -> bool:
        return _need_group_known(self.known, "current")

    @property
    def severity_known(self) -> bool:
        return _need_group_known(self.known, "severity")

    @property
    def functional_impact_known(self) -> bool:
        return _need_group_known(self.known, "functional_impact")

    @property
    def resolving(self) -> bool:
        if self.status == "resolved":
            return True
        current = (self.known.get("current") or self.known.get("status") or "").strip().lower()
        return current in {"improving", "resolved"}

    @property
    def known_dimension_count(self) -> int:
        return sum(
            (
                self.temporal_known,
                self.current_known,
                self.severity_known,
                self.functional_impact_known,
            )
        )

    @property
    def interrogation_eligible(self) -> bool:
        """Hard gate only: wrong subject / resolved episodes cannot be interrogated."""
        return self.speaker_owned and self.status != "resolved" and not self.resolving

    @property
    def has_open_questions(self) -> bool:
        """Unresolved askable needs exist (optional or obligatory)."""
        if not self.interrogation_eligible:
            return False
        return any(not self.need_known(need) for need in ASKABLE_NEEDS)

    @property
    def needs_attention(self) -> bool:
        """Backward-compatible alias for candidate generation."""
        return self.has_open_questions


@dataclass(frozen=True)
class PolicySnapshot:
    turn_number: int = 0
    episodes: tuple[EpisodeSnapshot, ...] = ()
    active_episode_id: str | None = None
    pending_episode_ids: tuple[str, ...] = ()
    pending_episode_attribute: str | None = None
    risk_level: str = "none"
    important_to_share_asked: bool = False
    important_to_share_resolved: bool = False
    background_goal_status: tuple[tuple[str, str], ...] = ()
    required_background_goals: tuple[str, ...] = ()
    mandatory_background_goals: bool = False
    wellness_entry_covered: bool = False
    probe_phase: str | None = None
    suspended_kind: str | None = None
    last_question_id: str | None = None
    last_question_intent: str | None = None
    last_question_slot: str | None = None
    # last_question_need remains for scorer/feature compat = last DELIVERED need.
    last_question_need: str | None = None
    # Explicit delivered need — never auto-copied from pending obligation.
    last_delivered_question_need: str | None = None
    recent_question_ids: tuple[str, ...] = ()
    questions_asked_this_episode: int = 0
    user_burden: float = 0.0
    call_closed: bool = False
    fsm_state: str = ""
    # Personal discourse evidence; defaults preserve all historical medical fixtures.
    thread_active: bool = False
    thread_statement: str = ""
    thread_utterance_id: str = ""
    thread_finished: bool = False
    thread_reply: bool = False
    thread_willing: bool = False
    thread_question_count: int = 0
    thread_resume_slot: str | None = None

    @property
    def its_pending(self) -> bool:
        return self.important_to_share_asked and not self.important_to_share_resolved

    @property
    def active_episode(self) -> EpisodeSnapshot | None:
        if not self.active_episode_id:
            return None
        return next((ep for ep in self.episodes if ep.episode_id == self.active_episode_id), None)

    @property
    def attention_episodes(self) -> tuple[EpisodeSnapshot, ...]:
        ordered: list[EpisodeSnapshot] = []
        if self.active_episode_id:
            ep = self.active_episode
            if ep and ep.needs_attention:
                ordered.append(ep)
        for ep_id in self.pending_episode_ids:
            ep = next((item for item in self.episodes if item.episode_id == ep_id), None)
            if ep and ep.needs_attention and ep not in ordered:
                ordered.append(ep)
        for ep in self.episodes:
            if ep.needs_attention and ep not in ordered:
                ordered.append(ep)
        return tuple(ordered)

    @property
    def interrogatable_episodes(self) -> tuple[EpisodeSnapshot, ...]:
        return tuple(ep for ep in self.episodes if ep.interrogation_eligible)

    def has_askable_open_issues(self, ctx: TurnContextView | None = None) -> bool:
        """
        Hard progression blocker — NOT "any optional unknown remains".

        Optional unresolved needs do not hard-block after intentional ITS leave.
        Pending obligations, reopenable fresh episodes, and new-turn evidence still do.
        """
        import packages.dialogue_engine.action_policy.need_value as need_value

        return need_value.has_hard_blocking_episode_work(self, ctx=ctx)

    def episode_decision_queue(self) -> tuple[EpisodeSnapshot, ...]:
        """Speaker-owned episodes in priority order: active → pending → remaining."""
        ordered: list[EpisodeSnapshot] = []
        if self.active_episode_id:
            ep = self.active_episode
            if ep and ep.speaker_owned:
                ordered.append(ep)
        for ep_id in self.pending_episode_ids:
            ep = self.episode(ep_id)
            if ep and ep.speaker_owned and ep not in ordered:
                ordered.append(ep)
        for ep in self.episodes:
            if (
                ep.speaker_owned
                and ep.interrogation_eligible
                and ep.has_open_questions
                and ep not in ordered
            ):
                ordered.append(ep)
        return tuple(ordered)

    def outstanding_pending_obligation(self) -> bool:
        import packages.dialogue_engine.action_policy.need_value as need_value

        return need_value.outstanding_pending_obligation(self)

    def best_remaining_ask_utility(self, ctx: TurnContextView | None = None) -> float:
        import packages.dialogue_engine.action_policy.need_value as need_value

        return need_value.best_remaining_ask_utility(self, ctx=ctx)

    def transition_preferred(self, ctx: TurnContextView) -> bool:
        """True when transition utility beats best remaining ask utility."""
        import packages.dialogue_engine.action_policy.need_value as need_value

        if self.episodes and not any(ep.speaker_owned for ep in self.episodes):
            return False
        owned = [ep for ep in self.episodes if ep.speaker_owned]
        if not owned:
            return False
        if all(ep.resolving for ep in owned):
            return True
        currently_askable = bool(need_value.currently_askable_needs(self, ctx=ctx))
        if not currently_askable:
            return True
        # Fresh speaker issue this turn: probe it before any transition.
        # (Mirrors the ITS hard block on new speaker issues — transitioning
        # while a brand-new episode is unprobed drops the lead, fs-1f6d3000.)
        if ctx.has_new_speaker_issue:
            return False
        if need_value.has_hard_blocking_episode_work(self, ctx=ctx):
            return need_value.transition_preferred(
                self,
                answer_pending=ctx.answers_pending_question,
                ctx=ctx,
            )
        return need_value.transition_preferred(
            self,
            answer_pending=ctx.answers_pending_question,
            ctx=ctx,
        )

    def episode(self, episode_id: str | None) -> EpisodeSnapshot | None:
        if episode_id is None:
            return None
        return next((ep for ep in self.episodes if ep.episode_id == episode_id), None)

    def background_status(self, goal: str) -> str:
        return dict(self.background_goal_status).get(goal, BackgroundGoalCoverage.UNSEEN.value)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> PolicySnapshot:
        eps = []
        for item in raw.get("episodes", ()):
            known = item.get("known_attributes", item.get("known", {}))
            eps.append(
                EpisodeSnapshot(
                    episode_id=item["episode_id"],
                    kind=item.get("kind", "symptom"),
                    status=item.get("status", "open"),
                    known_attributes=tuple(sorted((str(k), str(v)) for k, v in known.items())),
                    speaker_owned=bool(item.get("speaker_owned", True)),
                )
            )
        bg = raw.get("background_goal_status", {})
        return cls(
            turn_number=int(raw.get("turn_number", 0)),
            episodes=tuple(eps),
            active_episode_id=raw.get("active_episode_id"),
            pending_episode_ids=tuple(raw.get("pending_episode_ids", ())),
            pending_episode_attribute=raw.get("pending_episode_attribute"),
            risk_level=str(raw.get("risk_level", "none")),
            important_to_share_asked=bool(raw.get("important_to_share_asked", False)),
            important_to_share_resolved=bool(raw.get("important_to_share_resolved", False)),
            background_goal_status=tuple(sorted((str(k), str(v)) for k, v in bg.items())),
            required_background_goals=tuple(sorted(raw.get("required_background_goals", ()))),
            mandatory_background_goals=bool(raw.get("mandatory_background_goals", False)),
            wellness_entry_covered=bool(raw.get("wellness_entry_covered", False)),
            probe_phase=raw.get("probe_phase"),
            suspended_kind=raw.get("suspended_kind"),
            last_question_id=raw.get("last_question_id"),
            last_question_intent=raw.get("last_question_intent"),
            last_question_slot=raw.get("last_question_slot"),
            last_question_need=raw.get("last_question_need")
            or raw.get("last_delivered_question_need"),
            last_delivered_question_need=raw.get("last_delivered_question_need")
            or raw.get("last_question_need"),
            recent_question_ids=tuple(raw.get("recent_question_ids", ())),
            questions_asked_this_episode=int(raw.get("questions_asked_this_episode", 0)),
            user_burden=float(raw.get("user_burden", 0.0)),
            call_closed=bool(raw.get("call_closed", False)),
            fsm_state=str(raw.get("fsm_state", "")),
            thread_active=bool(raw.get("thread_active", False)),
            thread_statement=str(raw.get("thread_statement", "")),
            thread_utterance_id=str(raw.get("thread_utterance_id", "")),
            thread_finished=bool(raw.get("thread_finished", False)),
            thread_reply=bool(raw.get("thread_reply", False)),
            thread_willing=bool(raw.get("thread_willing", False)),
            thread_question_count=int(raw.get("thread_question_count", 0)),
            thread_resume_slot=raw.get("thread_resume_slot"),
        )


@dataclass(frozen=True)
class TurnContextView:
    raw_text: str = ""
    utterance_id: str = ""
    dialogue_act: str = "answer"
    control: str = "none"
    user_question: bool = False
    needs_clarification: bool = False
    answers_pending_question: bool = False
    has_new_issue: bool = False
    has_new_speaker_issue: bool = False
    has_new_other_person_issue: bool = False
    turn_risk_level: str = "none"
    has_goal_facts: bool = False
    correction: bool = False
    meta: bool = False
    clarify_target: str | None = None
    unresolved_concern: bool = False
    vague_negative_wellness: bool = False

    @property
    def repair(self) -> bool:
        return self.dialogue_act in {"repair", "repeat"}

    @property
    def explicit_farewell(self) -> bool:
        return self.control == "stop_call"

    @property
    def urgent_risk(self) -> bool:
        return self.turn_risk_level == "urgent"

    @property
    def has_grounded_information(self) -> bool:
        return (
            self.has_new_speaker_issue
            or self.has_new_other_person_issue
            or self.has_goal_facts
            or self.correction
        )

    @property
    def unclear_without_grounding(self) -> bool:
        return (
            self.dialogue_act in {"unclear", "backchannel"}
            and not self.has_grounded_information
            and not self.user_question
        )

    @classmethod
    def from_turn(cls, turn: object | None) -> TurnContextView:
        if turn is None:
            return cls()
        from packages.dialogue_engine.action_policy.semantic_signals import (
            classify_turn_issues,
            derive_turn_risk_level,
            derive_unresolved_concern,
            wellness_polarity_negative,
        )

        issue_mentions = tuple(getattr(turn, "issue_mentions", ()) or ())
        observations = tuple(getattr(turn, "observations", ()) or ())
        goal_facts = tuple(getattr(turn, "goal_facts", ()) or ())
        risk_candidates = tuple(getattr(turn, "risk_candidates", ()) or ())
        user_q = bool(getattr(turn, "user_question", None))
        dialogue_act = str(getattr(turn, "dialogue_act", "answer"))
        raw_text = str(getattr(turn, "raw_text", ""))
        speaker_issue, other_issue = classify_turn_issues(
            issue_mentions=issue_mentions,
            observations=observations,
        )
        grounded = bool(
            speaker_issue or other_issue or goal_facts or getattr(turn, "correction", False)
        )
        ambiguities = tuple(getattr(turn, "kernel_ambiguities", ()) or ())
        needs_clarification = bool(getattr(turn, "needs_clarification", False))
        vague_negative = wellness_polarity_negative(goal_facts) or "vague_issue" in ambiguities
        unresolved = derive_unresolved_concern(
            raw_text=raw_text,
            issue_mentions=issue_mentions,
            goal_facts=goal_facts,
            kernel_ambiguities=ambiguities,
            needs_clarification=needs_clarification,
            observations=observations,
        )
        return cls(
            raw_text=raw_text,
            utterance_id=str(getattr(turn, "utterance_id", "") or ""),
            dialogue_act=dialogue_act,
            control=str(getattr(turn, "control", "none")),
            user_question=user_q,
            needs_clarification=needs_clarification,
            answers_pending_question=bool(getattr(turn, "answers_pending_question", False)),
            has_new_issue=speaker_issue or other_issue,
            has_new_speaker_issue=speaker_issue,
            has_new_other_person_issue=other_issue,
            turn_risk_level=derive_turn_risk_level(
                raw_text=raw_text,
                risk_candidates=risk_candidates,
            ),
            has_goal_facts=bool(goal_facts),
            correction=bool(getattr(turn, "correction", False)),
            meta=(user_q or dialogue_act == "question") and not grounded,
            unresolved_concern=unresolved,
            vague_negative_wellness=vague_negative,
            clarify_target="concern" if unresolved else None,
        )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> TurnContextView:
        speaker_issue = bool(raw.get("has_new_speaker_issue", False))
        other_issue = bool(raw.get("has_new_other_person_issue", False))
        if not speaker_issue and not other_issue and raw.get("has_new_issue"):
            speaker_issue = True
        turn_risk = str(raw.get("turn_risk_level", "none"))
        if turn_risk == "none" and raw.get("urgent_risk"):
            turn_risk = "urgent"
        return cls(
            raw_text=str(raw.get("raw_text", "")),
            utterance_id=str(raw.get("utterance_id", "")),
            dialogue_act=str(raw.get("dialogue_act", "answer")),
            control=str(raw.get("control", "none")),
            user_question=bool(raw.get("user_question", False)),
            needs_clarification=bool(raw.get("needs_clarification", False)),
            answers_pending_question=bool(raw.get("answers_pending_question", False)),
            has_new_issue=speaker_issue or other_issue or bool(raw.get("has_new_issue", False)),
            has_new_speaker_issue=speaker_issue,
            has_new_other_person_issue=other_issue,
            turn_risk_level=turn_risk,
            has_goal_facts=bool(raw.get("has_goal_facts", False)),
            correction=bool(raw.get("correction", False)),
            meta=bool(raw.get("meta", False)),
            clarify_target=raw.get("clarify_target"),
            unresolved_concern=bool(raw.get("unresolved_concern", False)),
            vague_negative_wellness=bool(raw.get("vague_negative_wellness", False)),
        )


def _delivered_question_need(
    intent: str | None, semantic_need: QuestionNeed | None = None,
) -> str | None:
    """Map last delivered question intent → need. Never uses pending obligation."""
    if semantic_need is not None:
        # Current questions carry meaning with their identity. Intent-name
        # inference remains only for old serialized questions lacking it.
        from packages.dialogue_engine.action_policy.needs import normalize_attribute

        return None if semantic_need.is_compound else normalize_attribute(semantic_need.attribute)
    text = (intent or "").lower()
    if "duration" in text or "onset" in text:
        return "temporal"
    if "current" in text or "status" in text:
        return "current"
    if "severity" in text:
        return "severity"
    if "functional" in text or "impact" in text:
        return "functional_impact"
    if "concern" in text:
        return "concern"
    return None


def _pending_obligation_need(pending: str | None) -> str | None:
    if not pending:
        return None
    if pending in ("onset", "duration"):
        return "temporal"
    if pending in ("current", "status"):
        return "current"
    return pending


def _speaker_owned_episode(state: EngineState, episode_id: str) -> bool:
    seen = []
    for obs in state.observations.values():
        if getattr(obs, "episode_id", None) != episode_id:
            continue
        if getattr(obs, "attribute", None) != "issue":
            continue
        seen.append(_value(getattr(obs, "subject", "speaker")).lower())
    if not seen:
        return True
    return any(subject.endswith("speaker") or subject == "speaker" for subject in seen)


def _project_background_coverage(state: EngineState) -> dict[str, str]:
    """Read actual goal/slot dispositions before stale scheduler coverage.

    Personal selection bypasses the legacy coverage-sync side effect. A snapshot
    must therefore project terminal truth itself, without writing coverage or
    pretending that a decline/unknown outcome is a supplied health fact.
    """
    coverage = {str(key): _value(value) for key, value in state.background_goal_status.items()}
    terminal_lifecycles = {"DECLINED", "SKIPPED", "NOT_APPLICABLE", "UNCLEAR"}
    for slot in ("wellness", "mood", "sleep", "plans"):
        coverage.setdefault(slot, BackgroundGoalCoverage.UNSEEN.value)
        slot_status = _value(state.slots.get(slot, "")).upper()
        goals = tuple(goal for goal in state.goals.values() if goal.slot == slot)
        goal_statuses = {_value(goal.status).upper() for goal in goals}
        lifecycles = {_value(goal.lifecycle).upper() for goal in goals}
        if slot_status == "FILLED" or "FILLED" in goal_statuses or "SATISFIED" in lifecycles:
            coverage[slot] = BackgroundGoalCoverage.ANSWERED.value
        elif (
            slot_status != "OPEN"
            or any(status != "OPEN" for status in goal_statuses)
            or bool(lifecycles & terminal_lifecycles)
        ):
            coverage[slot] = BackgroundGoalCoverage.SKIPPED.value
    return coverage


def _wellness_covered(state: EngineState, coverage: Mapping[str, str] | None = None) -> bool:
    coverage = coverage if coverage is not None else _project_background_coverage(state)
    if state.slots.get("wellness") != SlotStatus.OPEN:
        return True
    if coverage.get("wellness") == BackgroundGoalCoverage.SKIPPED.value:
        return True  # terminal disposition, not an invented wellness value
    for slot in ("wellness", "mood", "sleep"):
        if coverage.get(slot) in {
            BackgroundGoalCoverage.ANSWERED.value,
            BackgroundGoalCoverage.COVERED_FROM_SPEECH.value,
        }:
            return True
    return False


def build_policy_snapshot(
    state: EngineState,
    ctx: TurnContextView | None = None,
) -> PolicySnapshot:
    """Read EngineState only; never calls mutating helpers."""
    episodes = tuple(
        EpisodeSnapshot(
            episode_id=ep.episode_id,
            kind=ep.kind,
            status=ep.status,
            known_attributes=tuple(
                sorted((str(k), str(v)) for k, v in ep.known_attributes.items())
            ),
            speaker_owned=_speaker_owned_episode(state, ep.episode_id),
        )
        for ep in sorted(state.issue_episodes.values(), key=lambda item: item.episode_id)
    )
    q = state.delivered_question or state.playing_question or state.planned_question
    delivered = state.delivered_question
    delivered_need = _delivered_question_need(
        delivered.intent, delivered.semantic_need,
    ) if delivered is not None else None
    recent = []
    for candidate in (state.delivered_question, state.playing_question, state.planned_question):
        if candidate and candidate.question_id not in recent:
            recent.append(candidate.question_id)
    q_count = 0
    if state.active_episode_id:
        prefix = f"episode_{state.active_episode_id}"
        for goal in state.goals.values():
            if str(goal.slot).startswith(prefix):
                q_count += int(goal.delivered_attempts)
    burden = min(1.0, (q_count / 4.0) + max(0, state.turn_seq - 6) * 0.05)
    background_coverage = _project_background_coverage(state)
    wellness_covered = _wellness_covered(state, background_coverage)
    thread_active = state.current_thread_label == "рассказ"
    thread_statement = str(getattr(state, "thread_last_statement", "") or "")[:240]
    thread_id = str(getattr(state, "thread_last_utterance_id", "") or "")
    thread_finished = bool(state.thread_reply_finished)
    current_id = ctx.utterance_id if ctx and ctx.utterance_id else thread_id
    resume_slot = next(
        (
            goal
            for goal in ("wellness", "mood", "sleep", "plans")
            if (state.mandatory_background_goals or goal in state.required_background_goals)
            and background_coverage.get(goal, BackgroundGoalCoverage.UNSEEN.value)
            in {"unseen", "asked"}
        ),
        None,
    )
    if (
        thread_active
        and state.slots.get("wellness") == SlotStatus.OPEN
        and background_coverage.get("wellness") in {"unseen", "asked"}
        and not wellness_covered
    ):
        # Wellness entry is an existing protocol obligation even in the short
        # preset. Deferring it for a story does not silently make it optional.
        resume_slot = "wellness"
    return PolicySnapshot(
        turn_number=state.turn_seq,
        episodes=episodes,
        active_episode_id=state.active_episode_id,
        pending_episode_ids=tuple(state.pending_episode_ids),
        pending_episode_attribute=state.pending_episode_attribute,
        risk_level="none",
        important_to_share_asked=state.important_to_share_asked,
        important_to_share_resolved=state.important_to_share_resolved,
        background_goal_status=tuple(sorted(background_coverage.items())),
        required_background_goals=tuple(sorted(state.required_background_goals)),
        mandatory_background_goals=state.mandatory_background_goals,
        wellness_entry_covered=wellness_covered,
        probe_phase=state.probe_phase,
        suspended_kind=state.suspended_obligation.kind if state.suspended_obligation else None,
        last_question_id=q.question_id if q else None,
        last_question_intent=q.intent if q else None,
        last_question_slot=q.slot if q else None,
        last_question_need=delivered_need,
        last_delivered_question_need=delivered_need,
        recent_question_ids=tuple(recent),
        questions_asked_this_episode=q_count,
        user_burden=burden,
        call_closed=state.call_closed,
        fsm_state=_value(state.fsm_state),
        thread_active=thread_active,
        thread_statement=thread_statement,
        thread_utterance_id=thread_id,
        thread_finished=thread_finished,
        thread_reply=bool(current_id and state.thread_reply_turn_id == current_id),
        thread_willing=bool(thread_active and thread_statement.strip() and not thread_finished),
        thread_question_count=state.thread_followup_count,
        thread_resume_slot=resume_slot,
    )
