"""Link semantic spans within a clause."""

from __future__ import annotations

from packages.dialogue_engine.semantic_kernel.types import (
    RelationType,
    SemanticRelation,
    SemanticSpan,
    SpanType,
)


def _nearest_issue(
    anchor: SemanticSpan, issues: list[SemanticSpan], *, max_distance: int = 80
) -> SemanticSpan | None:
    best: SemanticSpan | None = None
    best_dist = max_distance + 1
    for issue in issues:
        dist = min(abs(anchor.start - issue.start), abs(anchor.end - issue.end))
        if dist < best_dist:
            best_dist = dist
            best = issue
    return best


def parse_relations(spans: tuple[SemanticSpan, ...]) -> tuple[SemanticRelation, ...]:
    issues = [s for s in spans if s.type == SpanType.ISSUE]
    if not issues and not spans:
        return ()

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
            target = _nearest_issue(sp, issues, max_distance=40)
            if target:
                relations.append(
                    SemanticRelation(
                        type=RelationType.NEGATES,
                        source_span_id=sp.span_id,
                        target_span_id=target.span_id,
                        confidence=0.8,
                    )
                )

    if len(issues) >= 2:
        primary = issues[0]
        for extra in issues[1:]:
            relations.append(
                SemanticRelation(
                    type=RelationType.ASSOCIATED_WITH,
                    source_span_id=extra.span_id,
                    target_span_id=primary.span_id,
                    confidence=0.75,
                )
            )
    return tuple(relations)
