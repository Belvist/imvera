"""Subject resolution — per-issue/clause binding, never default other person to speaker."""

from __future__ import annotations

import re

from packages.dialogue_engine.semantic_kernel.clauses import clause_bounds
from packages.dialogue_engine.semantic_kernel.lexicon import (
    OTHER_PERSON_MARKERS,
    SPEAKER_MARKERS,
)
from packages.dialogue_engine.semantic_kernel.morphology import normalize_token
from packages.dialogue_engine.semantic_kernel.types import (
    RelationType,
    SemanticRelation,
    SemanticSpan,
    SpanType,
    SubjectKind,
)

_DOCTOR_QUOTE = re.compile(
    r"\b(?:врач|медсестр\w*|доктор)\s+сказал\w*|мне\s+сказал\w*\s+что\b",
    re.I,
)
_U_OTHER = re.compile(r"\bу\s+([а-яё\-]+)\b", re.I)
_QUOTED = re.compile(r'«[^»]*»|“[^”]*”|"[^"\n]*"')


def _subject_for_clause(clause: str, *, has_issue: bool) -> SubjectKind:
    lower = clause.lower()
    if _DOCTOR_QUOTE.search(lower):
        return SubjectKind.UNKNOWN

    for m in _U_OTHER.finditer(clause):
        person = normalize_token(m.group(1))
        if person in SPEAKER_MARKERS:
            return SubjectKind.SPEAKER
        if person in OTHER_PERSON_MARKERS or any(
            person.startswith(p[:3]) for p in OTHER_PERSON_MARKERS if len(p) >= 3
        ):
            return SubjectKind.OTHER_PERSON
        return SubjectKind.UNKNOWN

    tokens = [normalize_token(t) for t in re.findall(r"[а-яё\-]+", lower, re.I)]
    if any(t in OTHER_PERSON_MARKERS for t in tokens):
        return SubjectKind.OTHER_PERSON
    if any(t in SPEAKER_MARKERS for t in tokens) or "у меня" in lower:
        return SubjectKind.SPEAKER
    if has_issue:
        return SubjectKind.SPEAKER
    return SubjectKind.UNKNOWN


def resolve_subject(
    text: str,
    spans: tuple[SemanticSpan, ...],
) -> tuple[SubjectKind, tuple[SemanticRelation, ...]]:
    """Bind SUBJECT_OF per ISSUE span; global kind is only a coarse hint."""
    issues = [s for s in spans if s.type == SpanType.ISSUE]
    if not issues:
        clauses = clause_bounds(text)
        clause = clauses[0][2] if clauses else text
        return _subject_for_clause(clause, has_issue=False), ()

    subjects_by_position = resolve_issue_subjects(
        text, tuple(s.start for s in issues),
        body_positions=tuple(s.start for s in spans if s.type == SpanType.BODY_SITE),
    )
    relations: list[SemanticRelation] = []
    subjects: list[SubjectKind] = []

    for issue in issues:
        subject = subjects_by_position[issue.start]
        subjects.append(subject)
        if subject == SubjectKind.OTHER_PERSON:
            relations.append(
                SemanticRelation(
                    type=RelationType.SUBJECT_OF,
                    source_span_id=issue.span_id,
                    target_span_id="subj-other_person",
                    confidence=0.9,
                )
            )
        elif subject == SubjectKind.UNKNOWN:
            relations.append(
                SemanticRelation(
                    type=RelationType.SUBJECT_OF,
                    source_span_id=issue.span_id,
                    target_span_id="subj-unknown",
                    confidence=0.75,
                )
            )

    if all(s == SubjectKind.OTHER_PERSON for s in subjects):
        return SubjectKind.OTHER_PERSON, tuple(relations)
    if any(s == SubjectKind.OTHER_PERSON for s in subjects):
        return SubjectKind.OTHER_PERSON, tuple(relations)
    if all(s == SubjectKind.UNKNOWN for s in subjects):
        return SubjectKind.UNKNOWN, tuple(relations)
    return SubjectKind.SPEAKER, tuple(relations)


def resolve_issue_subjects(
    text: str, positions: tuple[int, ...], *, body_positions: tuple[int, ...] = (),
) -> dict[int, SubjectKind]:
    """Resolve implicit reports in their discourse, without assigning ambiguity.

    A relative's preceding clause removes the implicit-speaker default. Explicit
    self reference and a contrastive pivot can restore it. An additive return
    ("А ещё спина") requires an earlier owned issue, not merely an earlier "я".
    Literal quote words cannot establish the caller's subject.
    """
    quoted = [(m.start(), m.end()) for m in _QUOTED.finditer(text)]
    subjects: dict[int, SubjectKind] = {}
    previous_explicit = SubjectKind.UNKNOWN
    owned_issue = False
    previous_end = 0
    for start, end, clause in clause_bounds(text):
        visible = list(clause)
        for left, right in quoted:
            for offset in range(max(start, left), min(end, right)):
                visible[offset - start] = " "
        explicit = _subject_for_clause("".join(visible), has_issue=False)
        clause_positions = sorted({p for p in positions if start <= p < end})
        # The shared splitter removes conjunctions; recover grammar from the
        # original gap, never from a rewritten/concatenated evidence string.
        gap = text[previous_end:start].lower()
        words = re.findall(r"[а-яё]+", gap + " " + clause.lower())
        contrast = bool(words and words[0] in {"а", "но", "однако"})
        additive = "ещё" in words[:3] or "еще" in words[:3] or "также" in words[:3]
        connective_only = clause.lower() in {"а", "но", "однако"}
        body_pivot = any(start <= position < end for position in body_positions)
        for position in clause_positions:
            if any(left <= position < right for left, right in quoted):
                subject = SubjectKind.UNKNOWN
            elif explicit != SubjectKind.UNKNOWN:
                subject = explicit
            elif previous_explicit == SubjectKind.OTHER_PERSON:
                subject = (SubjectKind.SPEAKER if contrast and (
                    (body_pivot and not additive) or (owned_issue and (additive or connective_only))
                )
                           else SubjectKind.UNKNOWN)
            else:
                subject = _subject_for_clause(clause, has_issue=True)
            subjects[position] = subject
        owned_issue = owned_issue or any(subjects[p] == SubjectKind.SPEAKER
                                       for p in clause_positions)
        if explicit != SubjectKind.UNKNOWN:
            previous_explicit = explicit
        if not connective_only:
            previous_end = end
    return subjects


def subject_for_issue(
    issue_span_id: str,
    relations: tuple[SemanticRelation, ...],
    *,
    clause_subject: SubjectKind = SubjectKind.SPEAKER,
) -> SubjectKind:
    for rel in relations:
        if rel.type != RelationType.SUBJECT_OF:
            continue
        if rel.source_span_id != issue_span_id:
            continue
        if rel.target_span_id == "subj-other_person":
            return SubjectKind.OTHER_PERSON
        if rel.target_span_id == "subj-unknown":
            return SubjectKind.UNKNOWN
    return clause_subject
