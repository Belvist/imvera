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
from packages.dialogue_engine.state import EngineState

_REF = re.compile(
    r"\b(это|оно|там|эта\s+боль|эта\s+проблема|про\s+это|всё\s+ещё|все\s+ещё|"
    r"сейчас\s+уже\s+лучше|уже\s+лучше|получше)\b",
    re.I,
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
