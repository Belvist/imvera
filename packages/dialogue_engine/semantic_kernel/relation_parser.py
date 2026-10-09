"""Link semantic spans within a clause — no cross-clause misbinding."""

from __future__ import annotations

import re

from packages.dialogue_engine.semantic_kernel.clauses import clause_bounds
from packages.dialogue_engine.semantic_kernel.subject_resolver import _subject_for_clause
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
    negations = [s for s in spans if s.type == SpanType.NEGATION]

    relations: list[SemanticRelation] = []
    for sp in spans:
        if sp.type == SpanType.BODY_SITE:
            target = _nearest_issue(sp, issues)
            # A single anatomical subject can own coordinated predicates
            # («руки болят и трясутся»). Multiple sites keep nearest binding.
            bodies = [s for s in spans if s.type == SpanType.BODY_SITE]
            targets = [target] if target else []
            if len(bodies) == 1:
                targets.extend(issue for issue in issues if issue is not target
                               and issue.normalized in ("дрожать", "трястись"))
            for target in targets:
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
            # A directly negated degree («не очень», «не так сильно») is not
            # a severity value — linking it fabricates evidence (live:
            # «чувствую себя не очень» produced severity «очень»).
            if any(
                0 <= sp.start - neg.end <= 6
                for neg in negations
            ):
                continue
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
            bodies = [s for s in spans if s.type == SpanType.BODY_SITE]
            if sp.normalized == "нормально" and bodies and all(
                body.start > sp.end for body in bodies
            ):
                # «Поел нормально и руки ноют»: the later anatomical
                # subject cannot own the preceding independent assessment.
                continue
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
    previous = None
    for start, end, clause in clause_bounds(raw_text):
        clause_spans = tuple(s for s in spans if start <= s.start < end)
        relations.extend(_relations_in_clause(clause_spans))
        # A degree-only continuation may omit its subject («голова болит,
        # но терпимо»). Carry only one immediately preceding speaker issue;
        # never guess across another activity/person or multiple complaints.
        nominal_issues = [s for s in clause_spans if s.type == SpanType.ISSUE]
        nominal_pain = len(nominal_issues) == 1 and nominal_issues[0].normalized == "боль"
        from packages.dialogue_engine.issue_memory import clinical_issue_concept

        repeated_current_pain = (
            len(nominal_issues) == 1
            and clinical_issue_concept(
                nominal_issues[0].text, nominal_issues[0].normalized,
            ) == "pain"
            and any(s.type == SpanType.TIME and s.text.lower() == "сейчас" for s in clause_spans)
        )
        elliptic_pain = nominal_pain or repeated_current_pain
        if previous is not None and (not nominal_issues or elliptic_pain):

            pstart, pend, pclause = previous
            owners = [s for s in spans if s.type == SpanType.ISSUE and pstart <= s.start < pend]
            degrees = [s for s in clause_spans if s.type == SpanType.SEVERITY]
            status_updates = [s for s in clause_spans if s.type == SpanType.STATUS]
            status_continuation = bool(status_updates) and not nominal_issues and not degrees
            current_times = [s for s in clause_spans
                             if s.type == SpanType.TIME and s.text.lower() == "сейчас"]
            owner_bodies = [s for s in spans
                            if s.type == SpanType.BODY_SITE and pstart <= s.start < pend]
            owner_rest = pclause
            owned_spans = [s for s in spans if pstart <= s.start < pend and s.type in (
                SpanType.ISSUE, SpanType.BODY_SITE, SpanType.TIME, SpanType.DURATION,
                SpanType.SEVERITY, SpanType.STATUS,
            )]
            for owned in sorted(owned_spans, key=lambda s: s.start, reverse=True):
                a, b = owned.start - pstart, owned.end - pstart
                owner_rest = owner_rest[:a] + " " + owner_rest[b:]
            owner_words = re.findall(r"[а-яёa-z]+", owner_rest.lower())
            rest = clause
            omitted = degrees + current_times + (nominal_issues if elliptic_pain else [])
            if status_continuation:
                omitted += status_updates
            for degree in sorted(omitted, key=lambda s: s.start, reverse=True):
                a, b = degree.start - start, degree.end - start
                rest = rest[:a] + " " + rest[b:]
            words = re.findall(r"[а-яёa-z]+", rest.lower())
            if (
                len(owners) == 1 and (degrees or status_continuation or repeated_current_pain)
                and all(w in {"я", "у", "меня", "мне", "с", "со", "уже", "и", "а",
                              "ещё", "еще", "это", "но", "пока", "очень", "вполне", "довольно"}
                        for w in owner_words)
                and not any(s.type == SpanType.ACTIVITY and pstart <= s.start < pend
                            for s in spans)
                and not any(s.type in (SpanType.NEGATION, SpanType.UNCERTAINTY,
                                      SpanType.BODY_SITE, SpanType.ACTIVITY, SpanType.PERSON)
                            for s in clause_spans)
                and (not elliptic_pain or (
                    len(owner_bodies) == 1
                    and clinical_issue_concept(owners[0].text, owners[0].normalized) == "pain"
                ))
                and all(w in ({"но", "однако", "пока", "уже", "вполне", "это", "ещё", "еще",
                               "довольно"} | ({"всё", "все"} if status_continuation else set()))
                        for w in words)
                and not re.search(r"[.!?]", raw_text[pend:start])
                and _subject_for_clause(pclause, has_issue=True).value == "speaker"
                and not any(r.type == RelationType.NEGATES and r.target_span_id == owners[0].span_id
                            for r in relations)
            ):
                if elliptic_pain:
                    # A nominal restatement of ONE preceding pain inherits its
                    # grounded anatomical owner. The cross-clause BODY_OF is
                    # the explicit ellipsis link; no episode/active-slot guess.
                    relations.append(SemanticRelation(
                        type=RelationType.BODY_OF, source_span_id=owner_bodies[0].span_id,
                        target_span_id=nominal_issues[0].span_id, confidence=0.85,
                    ))
                    relations = [r for r in relations if not (
                        r.target_span_id == nominal_issues[0].span_id
                        and r.type in (RelationType.SEVERITY_OF, RelationType.ONSET_OF)
                    )]
                relations.extend(SemanticRelation(
                    type=RelationType.SEVERITY_OF, source_span_id=degree.span_id,
                    target_span_id=owners[0].span_id, confidence=0.85,
                ) for degree in degrees)
                relations.extend(SemanticRelation(
                    type=RelationType.ONSET_OF, source_span_id=when.span_id,
                    target_span_id=owners[0].span_id, confidence=0.85,
                ) for when in current_times)
                if status_continuation:
                    relations.extend(SemanticRelation(
                        type=RelationType.STATUS_OF, source_span_id=update.span_id,
                        target_span_id=owners[0].span_id, confidence=0.85,
                    ) for update in status_updates)
                if repeated_current_pain:
                    # Keep the original anatomical antecedent for a following
                    # degree clause; this repeated predicate is not a new owner.
                    continue
        previous = (start, end, clause)
    return tuple(relations)
