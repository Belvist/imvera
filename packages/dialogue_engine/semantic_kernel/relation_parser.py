"""Link semantic spans within a clause — no cross-clause misbinding."""

from __future__ import annotations

from packages.dialogue_engine.semantic_kernel.clauses import clause_bounds
from packages.dialogue_engine.semantic_kernel.types import (
    RelationType,
    SemanticRelation,
    SemanticSpan,
    SpanType,
)


def _nearest_issue(
    anchor: SemanticSpan,
    issues: list[SemanticSpan],
    *,
    max_distance: int = 80,
) -> SemanticSpan | None:
    best: SemanticSpan | None = None
    best_dist = max_distance + 1
    for issue in issues:
        dist = min(abs(anchor.start - issue.start), abs(anchor.end - issue.end))
        if dist < best_dist:
            best_dist = dist
            best = issue
    return best


def _relations_in_clause(spans: tuple[SemanticSpan, ...]) -> list[SemanticRelation]:
    issues = [s for s in spans if s.type == SpanType.ISSUE]
    if not issues:
        return []

    relations: list[SemanticRelation] = []
    for sp in spans:
        if sp.type == SpanType.BODY_SITE:
            target = _nearest_issue(sp, issues)
            if target:
                relations.append(
                    SemanticRelation(
                        type=RelationType.BODY_OF,
                        source_span_id=sp.span_id,
                        target_span_id=target.span_id,
                        confidence=min(sp.confidence, target.confidence),
                    )
                )
        elif sp.type == SpanType.TIME:
            target = _nearest_issue(sp, issues)
            if target:
                relations.append(
                    SemanticRelation(
                        type=RelationType.ONSET_OF,
                        source_span_id=sp.span_id,
                        target_span_id=target.span_id,
                        confidence=0.85,
                    )
                )
        elif sp.type == SpanType.DURATION:
            target = _nearest_issue(sp, issues)
            if target:
                relations.append(
                    SemanticRelation(
                        type=RelationType.DURATION_OF,
                        source_span_id=sp.span_id,
                        target_span_id=target.span_id,
                        confidence=0.85,
                    )
                )
        elif sp.type == SpanType.SEVERITY:
            target = _nearest_issue(sp, issues)
            if target:
                relations.append(
                    SemanticRelation(
                        type=RelationType.SEVERITY_OF,
                        source_span_id=sp.span_id,
                        target_span_id=target.span_id,
                        confidence=0.85,
                    )
                )
        elif sp.type == SpanType.STATUS:
            target = _nearest_issue(sp, issues)
            if target:
                relations.append(
                    SemanticRelation(
                        type=RelationType.STATUS_OF,
                        source_span_id=sp.span_id,
                        target_span_id=target.span_id,
                        confidence=0.85,
                    )
                )
        elif sp.type == SpanType.NEGATION:
            target = _nearest_issue(sp, issues, max_distance=8)
            if target and target.start > sp.start:
                relations.append(
                    SemanticRelation(
                        type=RelationType.NEGATES,
                        source_span_id=sp.span_id,
                        target_span_id=target.span_id,
                        confidence=0.8,
                    )
                )
    return relations


def parse_relations(
    spans: tuple[SemanticSpan, ...],
    *,
    raw_text: str = "",
) -> tuple[SemanticRelation, ...]:
    if not spans:
        return ()

    if not raw_text.strip():
        return tuple(_relations_in_clause(spans))

    relations: list[SemanticRelation] = []
    for start, end, _clause in clause_bounds(raw_text):
        clause_spans = tuple(s for s in spans if start <= s.start < end)
        relations.extend(_relations_in_clause(clause_spans))
    return tuple(relations)
