"""Build TurnContext snapshot from DialogueState for LLM interpreter."""

from __future__ import annotations

from packages.contracts.enums import AsrQuality, FsmState
from packages.contracts.semantic import (
    ActiveQuestionKind,
    ConfirmedFact,
    Evidence,
    FactCandidate,
    TurnContext,
)
from packages.dialogue.state import DialogueState


def _asr_label(q: AsrQuality) -> str:
    if q == AsrQuality.LOW:
        return "LOW"
    if q == AsrQuality.UNUSABLE:
        return "UNUSABLE"
    return "GOOD"


def active_question_kind(state: DialogueState) -> ActiveQuestionKind:
    if state.fsm_state == FsmState.IDENTIFY_PERSON:
        return "identity"
    if state.fsm_state == FsmState.CHECK_CONSENT:
        return "consent"
    if state.fsm_state == FsmState.CHECK_CAN_TALK:
        return "can_talk"
    if state.fsm_state in (FsmState.RED_SIGNAL, FsmState.CONFIRM_SITUATION):
        return "risk"
    if state.awaiting_goodbye_confirm or state.fsm_state == FsmState.GOODBYE:
        return "goodbye"
    if state.pending_slot:
        return "slot"
    return "none"


def _pending_question_text(state: DialogueState) -> str | None:
    if state.pending_question:
        return state.pending_question
    if state.fsm_state == FsmState.IDENTIFY_PERSON:
        return f"Я разговариваю с {state.elder_display_name}?"
    if state.fsm_state == FsmState.CHECK_CONSENT:
        return (
            "Вы согласны получать регулярные звонки от IMVERA? "
            "Это важно — звонки только с вашего согласия."
        )
    if state.fsm_state == FsmState.CHECK_CAN_TALK:
        return "Вам сейчас удобно немного поговорить?"
    if state.fsm_state in (FsmState.RED_SIGNAL, FsmState.CONFIRM_SITUATION):
        return state.risk_source_quote
    if state.pending_slot:
        from packages.dialogue.planner import _SLOT_QUESTIONS

        return _SLOT_QUESTIONS.get(state.pending_slot)
    return None


def build_turn_context(
    state: DialogueState,
    *,
    turn_id: int,
    utterance_id: str,
    raw_text: str,
    asr_quality: AsrQuality = AsrQuality.GOOD,
    delivered_phrases: tuple[str, ...] = (),
    question_delivery: str = "complete",
) -> TurnContext:
    confirmed: list[ConfirmedFact] = []
    for field, fact in state.facts.items():
        start = raw_text.find(fact.source_quote) if fact.source_quote else 0
        if start < 0:
            start = 0
        end = start + len(fact.source_quote or fact.value)
        confirmed.append(
            ConfirmedFact(
                observation_id=f"{state.call_id}:{field}:r{fact.revision}",
                source_utterance_id=utterance_id,
                revision=fact.revision,
                fact=FactCandidate(
                    field=field,
                    value=fact.value,
                    subject="speaker" if fact.subject == "elder" else fact.subject,
                    temporal_scope="today",
                    negated=fact.negated,
                    evidence=Evidence(
                        start=start,
                        end=max(start + 1, end),
                        quote=fact.source_quote or fact.value,
                    ),
                ),
            )
        )

    pending_id = state.pending_slot or (
        state.fsm_state.value if state.fsm_state != FsmState.CALL_START else None
    )
    qkind = active_question_kind(state)
    delivery: str = question_delivery
    if delivery == "complete" and qkind == "none":
        delivery = "unknown"

    return TurnContext(
        call_id=state.call_id,
        turn_id=turn_id,
        utterance_id=utterance_id,
        state_version=state.state_version,
        raw_text=raw_text,
        asr_quality=_asr_label(asr_quality),
        pending_question_id=pending_id,
        pending_question=_pending_question_text(state),
        pending_question_delivery=delivery,
        active_question_kind=qkind,
        confirmed_facts=tuple(confirmed),
        risk_episodes=(),
        delivered_assistant_phrases=delivered_phrases,
    )


def context_to_llm_dict(ctx: TurnContext) -> dict:
    return ctx.model_dump(mode="json")
