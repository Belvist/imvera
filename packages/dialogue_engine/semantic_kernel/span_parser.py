"""Generic span extraction — morphology + grammar, not body-specific branches."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from packages.dialogue_engine.semantic_kernel.clauses import clause_bounds
from packages.dialogue_engine.semantic_kernel.lexicon import (
    BODY_SITE_LEMMAS,
    ISSUE_VERB_LEMMAS,
)
from packages.dialogue_engine.semantic_kernel.morphology import normalize_token
from packages.dialogue_engine.semantic_kernel.types import SemanticSpan, SpanType

_TOKEN = re.compile(r"[а-яёa-z]+(?:-[а-яёa-z]+)?", re.I)

_DURATION = re.compile(
    r"\b("
    r"(?:первый|второй|третий|четвёртый|четвертый|пятый)\s+(?:день|час)|"
    r"\d+\s*(?:день|дня|дней|недел\w*|месяц\w*|год\w*|час\w*)|"
    r"пару\s+дней|несколько\s+дней"
    r")\b",
    re.I,
)
_TIME = re.compile(
    r"\b("
    r"сейчас|сегодня|вчерашн\w*|вчера|позавчерашн\w*|позавчера|"
    r"утром|вечером|ночью|"
    r"со?\s+вчерашн\w*(?:\s+дня)?|с\s+утра|с\s+десяти|с\s+\d{1,2}(?::\d{2})?|"
    r"\d{1,2}\s*:\s*\d{2}|"
    r"давно|иногда|периодически|постоянно|уже\s+почти|почти\s+прошл\w*|"
    r"три\s+года\s+назад|год\s+назад"
    r")\b",
    re.I,
)

_FALSE_ISSUE_TOKENS = frozenset(
    {
        "больше",
        "большое",
        "большой",
        "большая",
        "большие",
        "большим",
        "большими",
        "большого",
        "большую",
        "больном",
        "больной",
        "больница",
        "больницы",
        "болезнь",
        "болезни",
    }
)
_FALSE_BODY_SITE_TOKENS = frozenset({"голод", "голодный", "голодная", "голоден"})
_ISSUE_SURFACE = re.compile(
    r"^(бол\w*|приболел\w*|заболел\w*|разболел\w*|поболел\w*|побалива\w*|поныва\w*|прихватило|прихватыва\w*|схватило|схватыва\w*|вступило|ноет\w*|беспоко\w*|давит\w*|ломит\w*|тян\w*|перш\w*|"
    r"залож\w*|онем\w*|тошн\w*|кашл\w*|урч\w*|стрел\w*)$",
    re.I,
)
_SEVERITY = re.compile(
    r"\b(сильн\w*|терпим\w*|слаб\w*|невыносим\w*|ужасн\w*|пойд[её]т|сойд[её]т)\b",
    re.I,
)
_STATUS = re.compile(
    r"\b(прошл\w*|лучше|получше|нормально|уже\s+не\s+бол\w*|не\s+болит|"
    r"почти\s+не\s+бол\w*|залечил\w*|выздоров\w*)\b",
    re.I,
)
_NEGATION = re.compile(r"\b(не|ни)\b", re.I)
_UNCERTAINTY = re.compile(r"\b(наверное|вроде|кажется|может\s+быть)\b", re.I)
_ISSUE_PHRASE = re.compile(
    r"([а-яё\-]+(?:\s+[а-яё\-]+){0,2})\s+"
    r"(бол\w*|приболел\w*|заболел\w*|разболел\w*|поболел\w*|побалива\w*|поныва\w*|прихватило|прихватыва\w*|схватило|схватыва\w*|вступило|ноет\w*|беспоко\w*|давит\w*|ломит\w*|тян\w*|перш\w*|"
    r"залож\w*|онем\w*|тошн\w*|кашл\w*|урч\w*|стрел\w*)",
    re.I,
)
_ISSUE_BEFORE_BODY = re.compile(
    r"(бол\w*|приболел\w*|заболел\w*|разболел\w*|поболел\w*|побалива\w*|поныва\w*|прихватило|прихватыва\w*|схватило|схватыва\w*|вступило|ноет\w*|онем\w*|перш\w*|залож\w*|тян\w*|ломит\w*|давит\w*)\s+"
    r"(?:в|на|у)\s+([а-яё\-]+)",
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
        if stype == SpanType.BODY_SITE:
            lemma = _body_site_from_token(text) or " ".join(
                normalize_token(t) for t in _TOKEN.findall(text.lower())
            )
        else:
            lemma = " ".join(normalize_token(t) for t in _TOKEN.findall(text.lower()))
        sid = _sid()
        self.spans.append(
            SemanticSpan(
                span_id=sid,
                type=stype,
                text=text,
                start=start,
                end=end,
                normalized=lemma,
                confidence=conf,
            )
        )
        return sid


def _body_site_from_token(token: str) -> str | None:
    lemma = normalize_token(token)
    raw = token.lower()
    if raw in _FALSE_BODY_SITE_TOKENS:
        return None
    if lemma in BODY_SITE_LEMMAS:
        return lemma
    if len(raw) < 4:
        return None
    for site in BODY_SITE_LEMMAS:
        if len(site) < 4:
            continue
        if site[:4] == raw[:4] and abs(len(raw) - len(site)) <= 2:
            return site
    return None


def _issue_from_token(token: str) -> bool:
    lemma = normalize_token(token)
    raw = token.lower()
    if raw in _FALSE_ISSUE_TOKENS or lemma in _FALSE_ISSUE_TOKENS:
        return False
    if lemma in ISSUE_VERB_LEMMAS:
        return True
    if _ISSUE_SURFACE.match(raw):
        return True
    for verb in ISSUE_VERB_LEMMAS:
        stem = verb[:4]
        if len(stem) >= 4 and (raw.startswith(stem) or lemma.startswith(stem)):
            return True
    return False


def _pair_clause_body_issues(
    acc: _ParseAcc,
    clause: str,
    cstart: int,
) -> None:
    """Pair ISSUE verbs with nearest BODY_SITE lemma in the same clause."""
    tokens = [(m.group(0), cstart + m.start(), cstart + m.end()) for m in _TOKEN.finditer(clause)]
    issue_spans = [
        (tok, s, e) for tok, s, e in tokens if _issue_from_token(tok)
    ]
    body_spans = [
        (tok, s, e, _body_site_from_token(tok))
        for tok, s, e in tokens
        if _body_site_from_token(tok)
    ]
    for issue_t, is_, ie in issue_spans:
        acc.add(SpanType.ISSUE, issue_t, is_, ie, 0.9)
        if not body_spans:
            continue
        nearest = min(body_spans, key=lambda b: min(abs(b[1] - is_), abs(b[2] - ie)))
        acc.add(SpanType.BODY_SITE, nearest[0], nearest[1], nearest[2], 0.88)


def parse_spans(text: str) -> tuple[SemanticSpan, ...]:
    raw = text.strip()
    if not raw:
        return ()
    acc = _ParseAcc()

    duration_ranges: list[tuple[int, int]] = []
    for m in _DURATION.finditer(raw):
        duration_ranges.append((m.start(), m.end()))
        acc.add(SpanType.DURATION, m.group(0), m.start(), m.end(), 0.9)
    for m in _TIME.finditer(raw):
        if any(s <= m.start() < e or s < m.end() <= e for s, e in duration_ranges):
            continue
        acc.add(SpanType.TIME, m.group(0), m.start(), m.end(), 0.88)
    for m in _SEVERITY.finditer(raw):
        acc.add(SpanType.SEVERITY, m.group(0), m.start(), m.end(), 0.85)
    for m in _STATUS.finditer(raw):
        acc.add(SpanType.STATUS, m.group(0), m.start(), m.end(), 0.86)
    for m in _NEGATION.finditer(raw):
        acc.add(SpanType.NEGATION, m.group(0), m.start(), m.end(), 0.95)
    for m in _UNCERTAINTY.finditer(raw):
        acc.add(SpanType.UNCERTAINTY, m.group(0), m.start(), m.end(), 0.8)

    for cstart, cend, clause in clause_bounds(raw):

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
            body_tok = m.group(1).strip().split()[-1]
            site = _body_site_from_token(body_tok)
            if site:
                acc.add(SpanType.ISSUE, issue_text, istart, iend, 0.92)
                bstart = cstart + m.start(1) + m.group(1).rfind(body_tok)
                bend = bstart + len(body_tok)
                acc.add(SpanType.BODY_SITE, body_tok, bstart, bend, 0.9)

        for m in _BODY_PREP.finditer(clause):
            fragment = m.group(1)
            for tok in reversed(_TOKEN.findall(fragment)):
                site = _body_site_from_token(tok)
                if site:
                    tstart = cstart + m.start(1) + fragment.lower().rfind(tok.lower())
                    tend = tstart + len(tok)
                    acc.add(SpanType.BODY_SITE, tok, tstart, tend, 0.87)
                    break

        _pair_clause_body_issues(acc, clause, cstart)

        tokens = list(_TOKEN.finditer(clause))
        for tm in tokens:
            tok = tm.group(0)
            if _issue_from_token(tok):
                if not any(
                    s.type == SpanType.ISSUE and s.start == cstart + tm.start()
                    for s in acc.spans
                ):
                    acc.add(SpanType.ISSUE, tok, cstart + tm.start(), cstart + tm.end(), 0.84)

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
