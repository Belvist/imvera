"""RichUserTurn — canonical turn meaning for DialogueEngine."""

from __future__ import annotations

from pydantic import BaseModel

from packages.contracts.semantic import (
    Evidence,
    FactCandidate,
    IssueMention,
    RiskCandidate,
    SemanticPayload,
)
from packages.dialogue_engine.evidence_invariant import sanitize_issue_mention
from packages.dialogue_engine.issue_mention_extract import (
    detect_correction,
    detect_user_question,
    extract_goal_facts,
    extract_issue_mentions,
)
from packages.dialogue_engine.semantic_kernel.types import (
    Observation,
    SemanticRelation,
    SemanticSpan,
)


class RichUserTurn(BaseModel):
    utterance_id: str
    raw_text: str

    dialogue_act: str
    control: str
    consent_answer: str = "not_applicable"

    answers_pending_question: bool
    needs_clarification: bool

    user_question: str | None = None

    goal_facts: tuple[FactCandidate, ...] = ()
    issue_mentions: tuple[IssueMention, ...] = ()
    risk_candidates: tuple[RiskCandidate, ...] = ()

    correction: bool = False

    semantic_spans: tuple[SemanticSpan, ...] = ()
    semantic_relations: tuple[SemanticRelation, ...] = ()
    observations: tuple[Observation, ...] = ()
    kernel_confidence: float = 1.0
    kernel_ambiguities: tuple[str, ...] = ()
    kernel_level: int = 1
    kernel_route: str = ""
    kernel_elapsed_ms: float = 0.0
    kernel_corrections: tuple = ()

    model_config = {"frozen": True}


def enrich_payload_issue_mentions(
    payload: SemanticPayload,
    raw_text: str,
) -> SemanticPayload:
    """Validate LLM mentions; emergency regex fallback only when field is empty."""
    if payload.issue_mentions:
        validated = tuple(
            m
            for m in (
                sanitize_issue_mention(mention, raw_text)
                for mention in payload.issue_mentions
            )
            if m is not None
        )
        return payload.model_copy(update={"issue_mentions": validated})
    extracted = extract_issue_mentions(raw_text)
    if not extracted:
        return payload
    return payload.model_copy(update={"issue_mentions": extracted})


def payload_to_rich_turn(
    payload: SemanticPayload,
    *,
    utterance_id: str,
    raw_text: str,
) -> RichUserTurn:
    enriched = enrich_payload_issue_mentions(payload, raw_text)
    goal_facts = tuple(enriched.facts) or extract_goal_facts(raw_text)
    correction = enriched.dialogue_act == "correction" or detect_correction(raw_text)
    user_q = enriched.user_question or detect_user_question(raw_text)
    return RichUserTurn(
        utterance_id=utterance_id,
        raw_text=raw_text,
        dialogue_act=enriched.dialogue_act,
        control=enriched.control,
        consent_answer=enriched.consent_answer,
        answers_pending_question=enriched.answers_pending_question,
        needs_clarification=enriched.needs_clarification,
        user_question=user_q,
        goal_facts=goal_facts,
        issue_mentions=tuple(enriched.issue_mentions),
        risk_candidates=tuple(enriched.risk_candidates),
        correction=correction,
    )


def build_rich_turn_from_payload(
    payload: SemanticPayload,
    *,
    utterance_id: str,
    raw_text: str,
) -> RichUserTurn:
    return payload_to_rich_turn(payload, utterance_id=utterance_id, raw_text=raw_text)


def build_rich_turn_from_text(
    text: str,
    *,
    utterance_id: str,
    engine_state: object | None = None,
) -> RichUserTurn:
    """Semantic Kernel → RichUserTurn (canonical NLU path)."""
    from packages.dialogue_engine.semantic_kernel.kernel import interpret, kernel_to_rich_turn

    result = interpret(text, utterance_id=utterance_id, engine_state=engine_state)
    answer_slot = None
    if engine_state is not None and hasattr(engine_state, "answer_context_slot"):
        answer_slot = engine_state.answer_context_slot()
    turn = kernel_to_rich_turn(
        result,
        answer_slot=answer_slot,
        engine_state=engine_state,
    )
    if engine_state is not None and hasattr(engine_state, "answer_context_slot"):
        from packages.dialogue_engine.context import InterpretContext
        from packages.dialogue_engine.contextual_interpreter import contextual_interpret

        ctx = InterpretContext.from_engine_state(engine_state, turn_id=utterance_id)
        sem, confident = contextual_interpret(text.strip(), ctx)
        if confident and sem.slots:
            facts: list[FactCandidate] = []
            raw = text.strip()
            multi_slot = len(sem.slots) >= 2
            for slot_name, cand in sem.slots.items():
                if slot_name not in ("wellness", "mood", "sleep", "plans"):
                    continue
                if not multi_slot and answer_slot and slot_name != answer_slot:
                    continue
                value = cand.value or raw
                facts.append(
                    FactCandidate(
                        field=slot_name,
                        value=value,
                        subject="speaker",
                        temporal_scope="now",
                        negated=False,
                        evidence=Evidence(start=0, end=len(raw), quote=raw),
                    )
                )
            if facts:
                return turn.model_copy(update={"goal_facts": tuple(facts)})
    if turn.goal_facts or not answer_slot:
        return turn
    from packages.dialogue_engine.fast_interpreter import fast_interpret_semantic

    sem, confident = fast_interpret_semantic(text.strip(), answer_slot=answer_slot)
    if (
        not confident
        or not sem.target_slot
        or sem.target_slot not in ("wellness", "mood", "sleep", "plans")
    ):
        return turn
    value = sem.value or text.strip()
    fact = FactCandidate(
        field=sem.target_slot,
        value=value,
        subject="speaker",
        temporal_scope="now",
        negated=False,
        evidence=Evidence(start=0, end=len(text.strip()), quote=text.strip()),
    )
    return turn.model_copy(update={"goal_facts": (fact,)})


def build_rich_turn_from_text_legacy(text: str, *, utterance_id: str) -> RichUserTurn:
    """LEVEL0 compatibility helper — issue_mention_extract only."""
    raw = text.strip()
    dialogue_act = "answer"
    if detect_correction(raw):
        dialogue_act = "correction"
    elif detect_user_question(raw):
        dialogue_act = "question"
    elif raw.lower() in {"угу", "ага", "да", "нет"}:
        dialogue_act = "backchannel"
    payload = SemanticPayload(
        dialogue_act=dialogue_act,
        control="none",
        consent_answer="not_applicable",
        answers_pending_question=dialogue_act == "answer",
        needs_clarification=False,
        facts=extract_goal_facts(raw),
        issue_mentions=extract_issue_mentions(raw),
    )
    return payload_to_rich_turn(payload, utterance_id=utterance_id, raw_text=raw)


def rich_turn_has_episode_content(turn: RichUserTurn) -> bool:
    return bool(turn.issue_mentions) or turn.correction or turn.user_question
