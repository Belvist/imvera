"""Subject resolution — speaker vs other person vs unknown."""

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


def resolve_subject(
    text: str,
    spans: tuple[SemanticSpan, ...],
) -> tuple[SubjectKind, tuple[SemanticRelation, ...]]:
    lower = text.lower()
    if _DOCTOR_QUOTE.search(lower):
        return SubjectKind.UNKNOWN, ()

    tokens = [normalize_token(t) for t in re.findall(r"[а-яё\-]+", lower, re.I)]
    relations: list[SemanticRelation] = []

    for m in _U_OTHER.finditer(text):
        person = normalize_token(m.group(1))
        if person in OTHER_PERSON_MARKERS or any(
            person.startswith(p[:3]) for p in OTHER_PERSON_MARKERS if len(p) >= 3
        ):
            for sp in spans:
                if sp.type in (SpanType.ISSUE, SpanType.BODY_SITE) and sp.start >= m.start():
                    relations.append(
                        SemanticRelation(
                            type=RelationType.SUBJECT_OF,
                            source_span_id=sp.span_id,
                            target_span_id=f"subj-{person}",
                            confidence=0.9,
                        )
                    )
            return SubjectKind.OTHER_PERSON, tuple(relations)

    for marker in OTHER_PERSON_MARKERS:
        if marker in tokens:
            for sp in spans:
                if sp.type in (SpanType.ISSUE, SpanType.BODY_SITE):
                    relations.append(
                        SemanticRelation(
                            type=RelationType.SUBJECT_OF,
                            source_span_id=sp.span_id,
                            target_span_id=f"subj-{marker}",
                            confidence=0.88,
                        )
                    )
            return SubjectKind.OTHER_PERSON, tuple(relations)

    if any(t in SPEAKER_MARKERS for t in tokens) or "у меня" in lower:
        return SubjectKind.SPEAKER, tuple(relations)

    return SubjectKind.SPEAKER, tuple(relations)
