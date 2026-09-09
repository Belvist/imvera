"""Pronoun / reference resolution against active conversation memory."""

from __future__ import annotations

import re

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


def resolve_references(
    text: str,
    spans: tuple[SemanticSpan, ...],
    state: EngineState | None,
) -> tuple[SemanticRelation, ...]:
    if state is None or not state.active_episode_id:
        return ()
    ep = state.issue_episodes.get(state.active_episode_id)
    if ep is None:
        return ()
    relations: list[SemanticRelation] = []
    for m in _REF.finditer(text):
        ref_span = SemanticSpan(
            span_id=f"ref-{m.start()}",
            type=SpanType.TIME if "лучше" in m.group(0).lower() else SpanType.ISSUE,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            normalized=m.group(0).lower(),
            confidence=0.8,
        )
        relations.append(
            SemanticRelation(
                type=RelationType.REFERS_TO,
                source_span_id=ref_span.span_id,
                target_span_id=state.active_episode_id,
                confidence=0.78,
            )
        )
    return tuple(relations)
