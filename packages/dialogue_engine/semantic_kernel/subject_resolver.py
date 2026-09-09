"""Subject resolution — per-issue/clause binding, never default other person to speaker."""

from __future__ import annotations

import re

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
_CLAUSE_SPLIT = re.compile(r"\s*(?:[,;]|\s+и\s+|\s+а\s+)\s*", re.I)


def _clause_bounds(text: str) -> list[tuple[int, int, str]]:
    clauses: list[tuple[int, int, str]] = []
    offset = 0
    lower = text.lower()
    for part in _CLAUSE_SPLIT.split(text):
        part = part.strip()
        if not part:
            continue
        start = lower.find(part.lower(), offset)
        if start < 0:
            start = offset
        end = start + len(part)
        clauses.append((start, end, part))
        offset = end
    return clauses or [(0, len(text), text)]


def _clause_for_position(clauses: list[tuple[int, int, str]], pos: int) -> str:
    for start, end, clause in clauses:
        if start <= pos < end:
            return clause
    return clauses[-1][2] if clauses else ""


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
        clauses = _clause_bounds(text)
        clause = clauses[0][2] if clauses else text
        return _subject_for_clause(clause, has_issue=False), ()

    clauses = _clause_bounds(text)
    relations: list[SemanticRelation] = []
    subjects: list[SubjectKind] = []

    for issue in issues:
        clause = _clause_for_position(clauses, issue.start)
        subject = _subject_for_clause(clause, has_issue=True)
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
