"""Generic span extraction — morphology + grammar, not body-specific branches."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from packages.dialogue_engine.semantic_kernel.lexicon import (
    BODY_SITE_LEMMAS,
    ISSUE_VERB_LEMMAS,
)
from packages.dialogue_engine.semantic_kernel.morphology import normalize_token
from packages.dialogue_engine.semantic_kernel.types import SemanticSpan, SpanType

_CLAUSE_SPLIT = re.compile(r"\s*(?:[,;]|\s+и\s+|\s+а\s+также\s+|\s+ещё\s+|\s+еще\s+)\s*", re.I)
_TOKEN = re.compile(r"[а-яёa-z]+(?:-[а-яёa-z]+)?", re.I)

_TEMPORAL = re.compile(
    r"\b("
    r"сейчас|сегодня|вчера|позавчера|утром|вечером|ночью|"
    r"с\s+утра|с\s+десяти|с\s+\d{1,2}(?::\d{2})?|"
    r"\d{1,2}\s*:\s*\d{2}|"
    r"(?:первый|второй|третий|четвёртый|четвертый|пятый)\s+день|"
    r"\d+\s*(?:день|дня|дней|недел\w*|месяц\w*|год\w*|час\w*)|"
    r"давно|иногда|периодически|постоянно|уже\s+почти|почти\s+прошл\w*|"
    r"три\s+года\s+назад|год\s+назад"
    r")\b",
    re.I,
)
_SEVERITY = re.compile(r"\b(сильн\w*|терпим\w*|слаб\w*|невыносим\w*|ужасн\w*)\b", re.I)
_STATUS = re.compile(
    r"\b(прошл\w*|лучше|получше|нормально|уже\s+не\s+бол\w*|не\s+болит|"
    r"почти\s+не\s+бол\w*|залечил\w*|выздоров\w*)\b",
    re.I,
)
_NEGATION = re.compile(r"\b(не|ни)\b", re.I)
_UNCERTAINTY = re.compile(r"\b(наверное|вроде|кажется|может\s+быть)\b", re.I)
_ISSUE_PHRASE = re.compile(
    r"([а-яё\-]+(?:\s+[а-яё\-]+){0,3})\s+"
    r"(бол\w*|ноет\w*|беспоко\w*|давит\w*|ломит\w*|тян\w*|перш\w*|"
    r"залож\w*|онем\w*|тошн\w*|кашл\w*|урч\w*|стрел\w*)",
    re.I,
)
_ISSUE_BEFORE_BODY = re.compile(
    r"(бол\w*|ноет\w*|онем\w*|перш\w*|залож\w*|тян\w*|ломит\w*|давит\w*)\s+"
    r"([а-яё\-]+)",
    re.I,
)
_BODY_PREP = re.compile(
    r"\b(?:в|на|у)\s+([а-яё\-]+(?:\s+[а-яё\-]+){0,2})\b",
    re.I,
)


def _sid() -> str:
    return f"sp-{uuid.uuid4().hex[:8]}"


@dataclass
class _ParseAcc:
    spans: list[SemanticSpan] = field(default_factory=list)

    def add(self, stype: SpanType, text: str, start: int, end: int, conf: float = 0.9) -> str:
        norm = " ".join(normalize_token(t) for t in _TOKEN.findall(text.lower()))
        sid = _sid()
        self.spans.append(
            SemanticSpan(
                span_id=sid,
                type=stype,
                text=text,
                start=start,
                end=end,
                normalized=norm,
                confidence=conf,
            )
        )
        return sid


def _body_site_from_token(token: str) -> str | None:
    lemma = normalize_token(token)
    if lemma in BODY_SITE_LEMMAS:
        return lemma
    raw = token.lower()
    for site in BODY_SITE_LEMMAS:
        if raw.startswith(site[:4]) or site.startswith(lemma[:4]) or lemma.startswith(site[:4]):
            return site
    return None


def _issue_from_token(token: str) -> bool:
    lemma = normalize_token(token)
    if lemma in ISSUE_VERB_LEMMAS:
        return True
    raw = token.lower()
    for verb in ISSUE_VERB_LEMMAS:
        if raw.startswith(verb[:4]) or lemma.startswith(verb[:4]):
            return True
    return False


def parse_spans(text: str) -> tuple[SemanticSpan, ...]:
    raw = text.strip()
    if not raw:
        return ()
    acc = _ParseAcc()
    lower = raw.lower()

    for m in _TEMPORAL.finditer(raw):
        acc.add(SpanType.TIME, m.group(0), m.start(), m.end(), 0.88)
    for m in _SEVERITY.finditer(raw):
        acc.add(SpanType.SEVERITY, m.group(0), m.start(), m.end(), 0.85)
    for m in _STATUS.finditer(raw):
        acc.add(SpanType.STATUS, m.group(0), m.start(), m.end(), 0.86)
    for m in _NEGATION.finditer(raw):
        acc.add(SpanType.NEGATION, m.group(0), m.start(), m.end(), 0.95)
    for m in _UNCERTAINTY.finditer(raw):
        acc.add(SpanType.UNCERTAINTY, m.group(0), m.start(), m.end(), 0.8)

    clauses = _CLAUSE_SPLIT.split(raw)
    offset = 0
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            offset = lower.find(clause, offset) + len(clause) if clause else offset
            continue
        cstart = lower.find(clause.lower(), offset)
        if cstart < 0:
            cstart = offset
        cend = cstart + len(clause)

        for m in _ISSUE_BEFORE_BODY.finditer(clause):
            issue_text = m.group(1)
            body_tok = m.group(2)
            site = _body_site_from_token(body_tok)
            if site:
                acc.add(SpanType.ISSUE, issue_text, cstart + m.start(1), cstart + m.end(1), 0.91)
                acc.add(SpanType.BODY_SITE, body_tok, cstart + m.start(2), cstart + m.end(2), 0.89)

        for m in _ISSUE_PHRASE.finditer(clause):
            issue_text = m.group(2)
            istart = cstart + m.start(2)
            iend = cstart + m.end(2)
            acc.add(SpanType.ISSUE, issue_text, istart, iend, 0.92)
            body_tok = m.group(1).strip()
            site = _body_site_from_token(body_tok.split()[-1])
            if site:
                bstart = cstart + m.start(1)
                bend = cstart + m.end(1)
                acc.add(SpanType.BODY_SITE, body_tok, bstart, bend, 0.9)

        for m in _BODY_PREP.finditer(clause):
            fragment = m.group(1)
            for tok in _TOKEN.findall(fragment):
                site = _body_site_from_token(tok)
                if site:
                    tstart = cstart + m.start(1) + fragment.lower().find(tok.lower())
                    tend = tstart + len(tok)
                    acc.add(SpanType.BODY_SITE, tok, tstart, tend, 0.87)

        tokens = list(_TOKEN.finditer(clause))
        for tm in tokens:
            tok = tm.group(0)
            site = _body_site_from_token(tok)
            if site:
                acc.add(SpanType.BODY_SITE, tok, cstart + tm.start(), cstart + tm.end(), 0.82)
            if _issue_from_token(tok):
                acc.add(SpanType.ISSUE, tok, cstart + tm.start(), cstart + tm.end(), 0.84)

        offset = cend

    # Deduplicate overlapping same-type spans (keep longer)
    deduped: list[SemanticSpan] = []
    for sp in sorted(acc.spans, key=lambda s: (s.type, -len(s.text), s.start)):
        if any(
            o.type == sp.type and o.start <= sp.start < o.end and o.end >= sp.end
            for o in deduped
        ):
            continue
        deduped.append(sp)
    return tuple(sorted(deduped, key=lambda s: s.start))
