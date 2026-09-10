"""Immutable, generic policy snapshot built after semantic apply."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from packages.contracts.enums import SlotStatus
from packages.dialogue_engine.question_context import QuestionNeed
from packages.dialogue_engine.state import BackgroundGoalCoverage, CheckPath, EngineState


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
    def needs_attention(self) -> bool:
        """Generic low-burden rule: at most two useful dimensions for a mild open issue."""
        if not self.speaker_owned or self.status == "resolved" or self.resolving:
            return False
        if not self.temporal_known:
            return True
        return self.known_dimension_count < 2


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
    last_question_need: str | None = None
    recent_question_ids: tuple[str, ...] = ()
    questions_asked_this_episode: int = 0
    user_burden: float = 0.0
    call_closed: bool = False
    fsm_state: str = ""

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

    def episode(self, episode_id: str | None) -> EpisodeSnapshot | None:
        if episode_id is None:
            return None
        return next((ep for ep in self.episodes if ep.episode_id == episode_id), None)

    def background_status(self, goal: str) -> str:
        return dict(self.background_goal_status).get(goal, BackgroundGoalCoverage.UNSEEN.value)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PolicySnapshot":
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
            last_question_need=raw.get("last_question_need"),
            recent_question_ids=tuple(raw.get("recent_question_ids", ())),
            questions_asked_this_episode=int(raw.get("questions_asked_this_episode", 0)),
            user_burden=float(raw.get("user_burden", 0.0)),
            call_closed=bool(raw.get("call_closed", False)),
            fsm_state=str(raw.get("fsm_state", "")),
        )


@dataclass(frozen=True)
class TurnContextView:
    raw_text: str = ""
    dialogue_act: str = "answer"
    control: str = "none"
    user_question: bool = False
    needs_clarification: bool = False
    answers_pending_question: bool = False
    has_new_issue: bool = False
    has_goal_facts: bool = False
    correction: bool = False
    meta: bool = False
    clarify_target: str | None = None

    @property
    def repair(self) -> bool:
        return self.dialogue_act in {"repair", "repeat"}

    @property
    def explicit_farewell(self) -> bool:
        return self.control == "stop_call"

    @property
    def has_grounded_information(self) -> bool:
        return self.has_new_issue or self.has_goal_facts or self.correction

    @property
    def unclear_without_grounding(self) -> bool:
        return (
            self.dialogue_act in {"unclear", "backchannel"}
            and not self.has_grounded_information
            and not self.user_question
        )

    @classmethod
    def from_turn(cls, turn: object | None) -> "TurnContextView":
        if turn is None:
            return cls()
        issue_mentions = tuple(getattr(turn, "issue_mentions", ()) or ())
        goal_facts = tuple(getattr(turn, "goal_facts", ()) or ())
        user_q = bool(getattr(turn, "user_question", None))
        dialogue_act = str(getattr(turn, "dialogue_act", "answer"))
        grounded = bool(issue_mentions or goal_facts or getattr(turn, "correction", False))
        return cls(
            raw_text=str(getattr(turn, "raw_text", "")),
            dialogue_act=dialogue_act,
            control=str(getattr(turn, "control", "none")),
            user_question=user_q,
            needs_clarification=bool(getattr(turn, "needs_clarification", False)),
            answers_pending_question=bool(getattr(turn, "answers_pending_question", False)),
            has_new_issue=bool(issue_mentions),
            has_goal_facts=bool(goal_facts),
            correction=bool(getattr(turn, "correction", False)),
            meta=(user_q or dialogue_act == "question") and not grounded,
        )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "TurnContextView":
        return cls(
            raw_text=str(raw.get("raw_text", "")),
            dialogue_act=str(raw.get("dialogue_act", "answer")),
            control=str(raw.get("control", "none")),
            user_question=bool(raw.get("user_question", False)),
            needs_clarification=bool(raw.get("needs_clarification", False)),
            answers_pending_question=bool(raw.get("answers_pending_question", False)),
            has_new_issue=bool(raw.get("has_new_issue", False)),
            has_goal_facts=bool(raw.get("has_goal_facts", False)),
            correction=bool(raw.get("correction", False)),
            meta=bool(raw.get("meta", False)),
            clarify_target=raw.get("clarify_target"),
        )


def _last_question_need(intent: str | None, pending: str | None) -> str | None:
    if pending:
        if pending in ("onset", "duration"):
            return "temporal"
        if pending in ("current", "status"):
            return "current"
        return pending
    text = (intent or "").lower()
    if "duration" in text or "onset" in text:
        return "temporal"
    if "current" in text:
        return "current"
    if "severity" in text:
        return "severity"
    if "concern" in text:
        return "concern"
    return None


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


def _wellness_covered(state: EngineState) -> bool:
    if state.slots.get("wellness") != SlotStatus.OPEN:
        return True
    for slot in ("wellness", "mood", "sleep"):
        status = _value(
            state.background_goal_status.get(slot, BackgroundGoalCoverage.UNSEEN)
        )
        if status in {
            BackgroundGoalCoverage.ANSWERED.value,
            BackgroundGoalCoverage.COVERED_FROM_SPEECH.value,
        }:
            return True
        if state.slots.get(slot) == SlotStatus.FILLED:
            return True
    return False


def build_policy_snapshot(state: EngineState) -> PolicySnapshot:
    """Read EngineState only; never calls mutating helpers."""
    episodes = tuple(
        EpisodeSnapshot(
            episode_id=ep.episode_id,
            kind=ep.kind,
            status=ep.status,
            known_attributes=tuple(sorted((str(k), str(v)) for k, v in ep.known_attributes.items())),
            speaker_owned=_speaker_owned_episode(state, ep.episode_id),
        )
        for ep in sorted(state.issue_episodes.values(), key=lambda item: item.episode_id)
    )
    q = state.delivered_question or state.playing_question or state.planned_question
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
    risk = "urgent" if state.check_path == CheckPath.URGENT else "none"
    return PolicySnapshot(
        turn_number=state.turn_seq,
        episodes=episodes,
        active_episode_id=state.active_episode_id,
        pending_episode_ids=tuple(state.pending_episode_ids),
        pending_episode_attribute=state.pending_episode_attribute,
        risk_level=risk,
        important_to_share_asked=state.important_to_share_asked,
        important_to_share_resolved=state.important_to_share_resolved,
        background_goal_status=tuple(
            sorted((str(k), _value(v)) for k, v in state.background_goal_status.items())
        ),
        required_background_goals=tuple(sorted(state.required_background_goals)),
        mandatory_background_goals=state.mandatory_background_goals,
        wellness_entry_covered=_wellness_covered(state),
        probe_phase=state.probe_phase,
        suspended_kind=state.suspended_obligation.kind if state.suspended_obligation else None,
        last_question_id=q.question_id if q else None,
        last_question_intent=q.intent if q else None,
        last_question_slot=q.slot if q else None,
        last_question_need=_last_question_need(
            q.intent if q else None, state.pending_episode_attribute
        ),
        recent_question_ids=tuple(recent),
        questions_asked_this_episode=q_count,
        user_burden=burden,
        call_closed=state.call_closed,
        fsm_state=_value(state.fsm_state),
    )
