"""Build TurnContext snapshot from DialogueState for LLM interpreter."""

from __future__ import annotations

from packages.contracts.enums import AsrQuality
from packages.contracts.semantic import ConfirmedFact, Evidence, FactCandidate, TurnContext
from packages.dialogue.state import DialogueState


def _asr_label(q: AsrQuality) -> str:
    if q == AsrQuality.LOW:
        return "LOW"
    if q == AsrQuality.UNUSABLE:
        return "UNUSABLE"
    return "GOOD"


def build_turn_context(
    state: DialogueState,
    *,
    turn_id: int,
    utterance_id: str,
    raw_text: str,
    asr_quality: AsrQuality = AsrQuality.GOOD,
    delivered_phrases: tuple[str, ...] = (),
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

    pending_q = None
    pending_id = state.pending_slot
    if pending_id:
        from packages.dialogue.planner import _SLOT_QUESTIONS

        pending_q = _SLOT_QUESTIONS.get(pending_id)

    return TurnContext(
        call_id=state.call_id,
        turn_id=turn_id,
        utterance_id=utterance_id,
        state_version=state.state_version,
        raw_text=raw_text,
        asr_quality=_asr_label(asr_quality),
        pending_question_id=pending_id,
        pending_question=pending_q,
        pending_question_delivery="complete",
        confirmed_facts=tuple(confirmed),
        risk_episodes=(),
        delivered_assistant_phrases=delivered_phrases,
    )


def context_to_llm_dict(ctx: TurnContext) -> dict:
    return ctx.model_dump(mode="json")
