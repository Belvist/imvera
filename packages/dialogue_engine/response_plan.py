"""Canonical ResponsePlan — scheduler output, renderer input."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from packages.dialogue_engine import questions
from packages.dialogue_engine.question_context import QuestionNeed

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState


@dataclass
class ResponsePlan:
    """Single contract between scheduler and renderer."""

    obligation: str | None = None
    action: str = "speak"
    episode_id: str | None = None
    question_needs: list[QuestionNeed] = field(default_factory=list)
    acknowledge_facts: list[str] = field(default_factory=list)
    answer_user_question: str | None = None
    safety_class: str | None = None
    allowed_facts: list[str] = field(default_factory=list)
    prohibited_inferences: list[str] = field(default_factory=list)
    close_reason: str | None = None
    marks_question: bool = False
    intent: str = ""
    slot: str | None = None
    control: str | None = None
    suspend: object | None = None

    # Legacy compatibility for gradual migration
    acknowledge: str = ""
    facts_to_reference: list[str] = field(default_factory=list)
    next_slot: str | None = None
    mandatory_question: str = ""
    tone: str = "warm"
    clarification: bool = False


def render_response_plan(plan: ResponsePlan, state: EngineState) -> ResponsePlan:
    """Fill speakable text from plan obligations — policy does not hardcode strings."""
    if plan.action == "close_urgent":
        plan.mandatory_question = questions._URGENT_CLOSE
        plan.intent = "urgent_close"
        plan.marks_question = False
        return plan
    if plan.action == "close_summary":
        plan.mandatory_question = questions.summary_close_speech(
            state, acknowledge=plan.acknowledge
        )
        plan.intent = "summary"
        plan.marks_question = False
        return plan
    if plan.action == "close_partial":
        plan.mandatory_question = questions._PARTIAL_CLOSE
        plan.intent = "partial_unresolved_close"
        plan.marks_question = False
        return plan

    facts = plan.acknowledge_facts or plan.facts_to_reference
    ack = plan.acknowledge or _acknowledge_fills(state, facts)
    question = plan.mandatory_question

    if plan.answer_user_question:
        question = plan.answer_user_question
        plan.intent = plan.intent or "answer_user_question"
    elif plan.question_needs and not question:
        need = plan.question_needs[0]
        question = _question_for_need(state, plan, need)
    elif plan.next_slot and not question:
        question = questions.slot_question(plan.next_slot, state=state)
        plan.intent = plan.intent or f"check_{plan.next_slot}"
        plan.slot = plan.slot or plan.next_slot
        plan.marks_question = True
    elif plan.slot and not question:
        if plan.slot.startswith("probe_"):
            phase = plan.slot.removeprefix("probe_")
            question = questions.probe_question(phase, clarification=plan.clarification)
            plan.intent = plan.intent or plan.slot
        elif plan.slot in ("wellness", "mood", "sleep", "plans"):
            question = questions.slot_question(plan.slot, state=state)
            plan.intent = plan.intent or f"check_{plan.slot}"

    parts = [p for p in (ack, question) if p]
    plan.acknowledge = ack
    plan.mandatory_question = question
    if parts and not hasattr(plan, "_composed"):
        plan._composed = " ".join(parts)  # type: ignore[attr-defined]
    return plan


def composed_text(plan: ResponsePlan) -> str:
    parts = [p for p in (plan.acknowledge, plan.mandatory_question) if p]
    return " ".join(parts)


def build_response_plan(
    state: EngineState,
    *,
    newly_filled: list[str],
    next_slot: str,
) -> ResponsePlan:
    """Legacy helper — prefer schedule_next_action."""
    return ResponsePlan(
        obligation="background_goal",
        acknowledge_facts=newly_filled,
        next_slot=next_slot,
        marks_question=True,
    )


def compose_speech(plan: ResponsePlan, state: EngineState | None = None) -> str:
    from packages.dialogue_engine.state import EngineState as ES

    st = state if state is not None else ES(call_id="compose")
    return composed_text(render_response_plan(plan, st))


def _dummy_state() -> EngineState:
    from packages.dialogue_engine.state import EngineState

    return EngineState(call_id="render")


def _compound_question_text(ep, need: QuestionNeed) -> str:
    label = ep.primary_label.lower() if ep else ""
    attrs = set(need.attributes)
    if attrs >= {"duration", "current"} or attrs >= {"onset", "current"}:
        if "голов" in label:
            return (
                "Когда началась головная боль и сейчас ещё беспокоит или уже стало лучше?"
            )
        return "Когда это началось и сейчас всё ещё беспокоит или уже стало лучше?"
    return "Расскажите, пожалуйста, чуть подробнее."


def _question_for_need(state: EngineState, plan: ResponsePlan, need: QuestionNeed) -> str:
    from packages.dialogue_engine.conversation_policy import episode_question_for_attribute

    ep = state.issue_episodes.get(plan.episode_id) if plan.episode_id else None
    if need.is_compound:
        text = _compound_question_text(ep, need)
        plan.intent = "episode_compound_temporal_current"
        plan.slot = plan.intent
        plan.marks_question = True
        return text
    if ep is not None:
        text, intent = episode_question_for_attribute(ep, need.attribute)
        plan.intent = intent
        plan.slot = intent
        plan.marks_question = True
        return text
    if need.attribute in ("concern", "pain_night", "duration"):
        return questions.probe_question(need.attribute)
    return questions.slot_question(need.attribute, state=state)


def _acknowledge_fills(state: EngineState, filled: list[str]) -> str:
    if not filled:
        return ""

    if "wellness" in filled:
        rec = state.slot_records.get("wellness")
        pol = rec.polarity if rec else None
        val = rec.value if rec else state.slot_values.get("wellness", "")
        return questions.wellness_ack(polarity=pol, value=val)

    if "sleep" in filled:
        rec = state.slot_records.get("sleep")
        pol = rec.polarity if rec else None
        if pol == "negative" or _looks_bad_sleep(rec.value if rec else ""):
            return "Понимаю, ночь была тяжёлая."

    if "mood" in filled:
        rec = state.slot_records.get("mood")
        pol = rec.polarity if rec else None
        if pol == "negative":
            return "Понимаю."

    if "plans" in filled:
        return "Хорошо, поняла."

    return ""


def _looks_bad_sleep(text: str) -> bool:
    t = text.lower()
    return any(x in t for x in ("не спал", "плохо", "мало", "беспокойн", "почти не"))


def slot_polarity_from_candidate(cand) -> str | None:
    return cand.polarity
