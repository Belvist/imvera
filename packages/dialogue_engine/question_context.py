"""Canonical question obligations — scheduler must not fake episode attributes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

# Include полегче / полегче-forms: bare \bлегче\b does not match inside «полегче».
_RESOLVED_UTTERANCE = re.compile(
    r"\b("
    r"не\s+болит|уже\s+не\s+бол|боль\s+прошл\w*|всё\s+прошл\w*|все\s+прошл\w*|"
    r"прошл\w*|полегче|получше|легче|лучше|уже\s+почти\s+не|почти\s+прошл\w*"
    r")\b",
    re.I,
)

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState, IssueEpisode

# Semantic question model: a spoken question may be satisfied by any accepted semantics.
_QUESTION_NEEDS: dict[str, tuple[str, ...]] = {
    "onset": ("onset", "duration"),
    "duration": ("duration", "onset"),
    "severity": ("severity",),
    "current": ("current", "status"),
    "concern": ("concern",),
    "pain_night": ("pain_night",),
    "needs_help": ("needs_help",),
}


class QuestionKind(StrEnum):
    BACKGROUND_SLOT = "background_slot"
    EPISODE_ATTRIBUTE = "episode_attribute"
    TOPIC = "topic"
    PROBE = "probe"
    SAFETY = "safety"
    IDENTITY = "identity"
    REPAIR = "repair"


@dataclass(frozen=True)
class QuestionNeed:
    attributes: tuple[str, ...]
    accepted_semantics: tuple[str, ...]

    @property
    def attribute(self) -> str:
        return self.attributes[0]

    @property
    def is_compound(self) -> bool:
        return len(self.attributes) > 1

    @classmethod
    def for_attribute(cls, attribute: str) -> QuestionNeed:
        accepted = _QUESTION_NEEDS.get(attribute, (attribute,))
        return cls(attributes=(attribute,), accepted_semantics=accepted)

    @classmethod
    def compound(cls, *attributes: str) -> QuestionNeed:
        seen: set[str] = set()
        for attr in attributes:
            seen.update(_QUESTION_NEEDS.get(attr, (attr,)))
        return cls(attributes=attributes, accepted_semantics=tuple(seen))


def question_need_satisfied(ep: IssueEpisode, need: QuestionNeed) -> bool:
    """True when every attribute group in the need is satisfied."""
    if need.is_compound:
        return all(attribute_need_satisfied(ep, attr) for attr in need.attributes)
    return attribute_need_satisfied(ep, need.attribute)


@dataclass(frozen=True)
class QuestionContext:
    question_id: str
    kind: QuestionKind
    text: str
    semantic_need: QuestionNeed | None = None
    episode_id: str | None = None
    attribute: str | None = None
    slot: str | None = None
    intent: str | None = None
    retry_count: int = 0


def utterance_indicates_resolved(text: str) -> bool:
    """User text means the symptom is no longer active."""
    return bool(_RESOLVED_UTTERANCE.search(text.strip()))


def current_value_indicates_resolved(value: str) -> bool:
    raw = (value or "").strip().lower()
    if raw in ("resolved", "improving"):
        return True
    return utterance_indicates_resolved(raw)


def episode_is_resolved(ep: IssueEpisode) -> bool:
    if ep.status == "resolved":
        return True
    current = ep.known_attributes.get("current")
    if current and current_value_indicates_resolved(str(current)):
        return True
    return False


def mark_episode_resolved(ep: IssueEpisode) -> None:
    ep.known_attributes["current"] = "resolved"
    ep.status = "resolved"


def attribute_need_satisfied(ep: IssueEpisode, attribute: str) -> bool:
    """True when any accepted semantic type is present on the episode."""
    need = QuestionNeed.for_attribute(attribute)
    return any(ep.known_attributes.get(name) for name in need.accepted_semantics)


def episode_obligations_satisfied(ep: IssueEpisode) -> bool:
    """Episode has enough grounded facts to leave active questioning."""
    from packages.dialogue_engine.issue_memory import _needs_severity

    if episode_is_resolved(ep):
        return True
    if ep.kind == "symptom":
        temporal_ok = (
            attribute_need_satisfied(ep, "onset")
            or attribute_need_satisfied(ep, "duration")
        )
        if not temporal_ok:
            return False
        label = ep.primary_label.lower()
        # Headache: current/trend is required before severity (MVP severity_trend).
        if "голов" in label and not attribute_need_satisfied(ep, "current"):
            return False
        if _needs_severity(ep) and "severity" not in ep.known_attributes:
            return False
        if ep.body_site == "живот" and "current" not in ep.known_attributes:
            return False
        return True
    if ep.kind == "other":
        return bool(ep.known_attributes.get("needs_help"))
    if ep.kind == "sleep_problem":
        # «Плохо спал» already carries quality — one soft follow-up max, or done.
        if attribute_need_satisfied(ep, "quality") or attribute_need_satisfied(
            ep, "pattern"
        ):
            return True
        label = ep.primary_label.lower()
        if any(x in label for x in ("плох", "бессон", "не спал")):
            return True
        return False
    return bool(ep.known_attributes)


def question_context_from_state(state: EngineState) -> QuestionContext | None:
    """Build repair/speech context from delivered question or pending obligation."""
    from packages.dialogue_engine import questions
    from packages.dialogue_engine.topic_tracker import is_topic_slot

    delivered = state.delivered_question
    if delivered is not None:
        kind = QuestionKind.BACKGROUND_SLOT
        attribute = None
        episode_id = None
        semantic_need = None
        if delivered.slot.startswith("episode_"):
            kind = QuestionKind.EPISODE_ATTRIBUTE
            attribute = state.pending_episode_attribute
            if state.active_episode_id:
                episode_id = state.active_episode_id
            if attribute:
                semantic_need = QuestionNeed.for_attribute(attribute)
        elif is_topic_slot(delivered.slot):
            kind = QuestionKind.TOPIC
        elif delivered.slot.startswith("probe_"):
            kind = QuestionKind.PROBE
            attribute = delivered.slot.removeprefix("probe_")
            semantic_need = QuestionNeed.for_attribute(attribute)
        return QuestionContext(
            question_id=delivered.question_id,
            kind=kind,
            text=delivered.text,
            semantic_need=semantic_need,
            episode_id=episode_id,
            attribute=attribute,
            slot=delivered.slot,
            intent=delivered.intent,
        )

    if state.pending_episode_attribute and state.active_episode_id:
        ep = state.issue_episodes.get(state.active_episode_id)
        if ep is not None:
            from packages.dialogue_engine.conversation_policy import episode_question_for_attribute

            attr = state.pending_episode_attribute
            text, intent = episode_question_for_attribute(ep, attr)
            return QuestionContext(
                question_id=f"pending-{state.active_episode_id}-{attr}",
                kind=QuestionKind.EPISODE_ATTRIBUTE,
                text=text,
                semantic_need=QuestionNeed.for_attribute(attr),
                episode_id=state.active_episode_id,
                attribute=attr,
                slot=intent,
                intent=intent,
            )

    if state.probe_phase:
        text = questions.probe_question(state.probe_phase)
        return QuestionContext(
            question_id=f"probe-{state.probe_phase}",
            kind=QuestionKind.PROBE,
            text=text,
            semantic_need=QuestionNeed.for_attribute(state.probe_phase),
            slot=f"probe_{state.probe_phase}",
            intent=f"probe_{state.probe_phase}",
            attribute=state.probe_phase,
        )

    slot = state.answer_context_slot()
    if slot and not slot.startswith("episode_"):
        if is_topic_slot(slot):
            text = questions.topic_question(
                state.delivered_question.intent if state.delivered_question else slot
            )
            return QuestionContext(
                question_id=f"topic-{slot}",
                kind=QuestionKind.TOPIC,
                text=text,
                slot=slot,
            )
        if slot in ("wellness", "mood", "sleep", "plans"):
            return QuestionContext(
                question_id=f"slot-{slot}",
                kind=QuestionKind.BACKGROUND_SLOT,
                text=questions.slot_question(slot, state=state),
                slot=slot,
                intent=f"check_{slot}",
            )
    return None


def repair_question_text(state: EngineState, fallback_slot: str = "wellness") -> str:
    """Text to repeat on repair — never derives from unknown dynamic slot keys."""
    ctx = question_context_from_state(state)
    if ctx is not None and ctx.text.strip():
        return ctx.text
    from packages.dialogue_engine import questions
    from packages.dialogue_engine.topic_tracker import is_topic_slot

    if fallback_slot.startswith("probe_"):
        return questions.probe_question(fallback_slot.removeprefix("probe_"))
    if is_topic_slot(fallback_slot):
        return questions.topic_question(fallback_slot)
    if fallback_slot in ("wellness", "mood", "sleep", "plans"):
        return questions.slot_question(fallback_slot, state=state)
    return "Повторите, пожалуйста, коротко."
