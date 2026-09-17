"""Pronoun / reference resolution against active conversation memory."""

from __future__ import annotations

import re
import uuid

from packages.dialogue_engine.semantic_kernel.types import (
    RelationType,
    SemanticRelation,
    SemanticSpan,
    SpanType,
)
from packages.dialogue_engine.state import EngineState, QuestionPhase

_REF = re.compile(
    r"\b(это|оно|там|эта\s+боль|эта\s+проблема|про\s+это|всё\s+ещё|все\s+ещё|"
    r"сейчас\s+уже\s+лучше|уже\s+лучше|получше)\b",
    re.I,
)


def is_exclusive_topic_reference(
    text: str,
    spans: tuple[SemanticSpan, ...],
    relations: tuple[SemanticRelation, ...],
    state: EngineState | None,
) -> bool:
    if state is None or state.call_closed or state.pending_episode_attribute:
        return False
    question = state.delivered_question
    if (
        question is None
        or question.phase != QuestionPhase.DELIVERED
        or question.slot != "important_to_share"
        or question.intent not in ("important_to_share", "important_to_share_listen")
        or state.answer_context_slot() != "important_to_share"
        or not state.important_to_share_asked
        or state.important_to_share_resolved
    ):
        return False
    if len(state.issue_episodes) != 1 or state.pending_episode_ids:
        return False
    episode = state.issue_episodes.get(state.active_episode_id or "")
    if (
        episode is None
        or episode.subject != "speaker"
        or not episode.evidence_turn_ids
        or not any(mention.evidence.quote for mention in episode.mentions)
    ):
        return False
    refs = [relation for relation in relations if relation.type == RelationType.REFERS_TO]
    if len(refs) != 1 or refs[0].target_span_id != episode.episode_id:
        return False
    ref = next((span for span in spans if span.span_id == refs[0].source_span_id), None)
    if ref is None or ref.normalized not in ("это", "оно"):
        return False
    if any(span.span_id != ref.span_id for span in spans):
        return False
    tokens = text.lower().strip().rstrip(".!").split()
    exclusive = {"только", "лишь"}
    copula = {"было"}
    return (
        sum(token in exclusive for token in tokens) == 1
        and tokens.count(ref.normalized) == 1
        and sum(token in copula for token in tokens) <= 1
        and all(token in exclusive | copula | {ref.normalized} for token in tokens)
        and tokens.index(ref.normalized) > 0
        and tokens[tokens.index(ref.normalized) - 1] in exclusive
    )


def _sid() -> str:
    return f"ref-{uuid.uuid4().hex[:8]}"


def resolve_references(
    text: str,
    spans: tuple[SemanticSpan, ...],
    state: EngineState | None,
) -> tuple[tuple[SemanticSpan, ...], tuple[SemanticRelation, ...]]:
    if state is None or not state.active_episode_id:
        return (), ()
    ep = state.issue_episodes.get(state.active_episode_id)
    if ep is None:
        return (), ()

    ref_spans: list[SemanticSpan] = []
    relations: list[SemanticRelation] = []
    for m in _REF.finditer(text):
        is_status = "лучше" in m.group(0).lower() or "получше" in m.group(0).lower()
        ref_span = SemanticSpan(
            span_id=_sid(),
            type=SpanType.STATUS if is_status else SpanType.TIME,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            normalized=m.group(0).lower(),
            confidence=0.8,
        )
        ref_spans.append(ref_span)
        relations.append(
            SemanticRelation(
                type=RelationType.REFERS_TO,
                source_span_id=ref_span.span_id,
                target_span_id=state.active_episode_id,
                confidence=0.78,
            )
        )
    return tuple(ref_spans), tuple(relations)
