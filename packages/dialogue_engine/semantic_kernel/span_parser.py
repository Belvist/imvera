"""Generic span extraction — morphology + grammar, not body-specific branches."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from packages.dialogue_engine.semantic_kernel.clauses import clause_bounds
from packages.dialogue_engine.semantic_kernel.lexicon import (
    BODY_SITE_LEMMAS,
    ISSUE_VERB_LEMMAS,
    SENSATION_ADJECTIVES,
    SENSATION_NOUNS,
    SEVERITY_WORDS,
    TIME_WORDS,
)
from packages.dialogue_engine.semantic_kernel.morphology import normalize_token
from packages.dialogue_engine.semantic_kernel.types import SemanticSpan, SpanType

_TOKEN = re.compile(r"[а-яёa-z]+(?:-[а-яёa-z]+)?", re.I)


def _yo_variants(words: frozenset[str]) -> list[str]:
    """Both ё- and е-forms: span matching runs on raw text (no normalization)."""
    out: list[str] = []
    seen: set[str] = set()
    for w in sorted(words):
        for v in (w, w.replace("ё", "е"), w.replace("е", "ё")):
            if v not in seen:
                seen.add(v)
                out.append(v)
    return out

_DURATION = re.compile(
    r"\b("
    r"(?:первый|второй|третий|четвёртый|четвертый|пятый)\s+(?:день|час)|"
    r"(?:\d+|один|одна|одну|два|две|три|четыре|пять|шесть|семь|восемь|"
    r"девять|десять|полтора|полторы)\s*(?:день|дня|дней|недел\w*|месяц\w*|год\w*|час\w*|минут\w*)|"
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
    r"три\s+года\s+назад|год\s+назад|"
    + "|".join(_yo_variants(TIME_WORDS))
    + r")\b",
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
        # Comparative «более/менее» collides with the «боле» stem of болеть —
        # never a symptom by itself (live: «Более-менее.» ≠ pain).
        "более",
        "менее",
        "более-менее",
        # Yeast («дрожжи») collides with the «дрожь» stem — baking is not
        # a symptom («пеку пироги на дрожжах»).
        "дрожжи",
        "дрожжей",
    }
)
_FALSE_BODY_SITE_TOKENS = frozenset({"голод", "голодный", "голодная", "голоден"})
_ISSUE_SURFACE = re.compile(
    r"^(бол(?!ее(?:\b|-))\w*|приболел\w*|заболел\w*|разболел\w*|поболел\w*|побалива\w*|поныва\w*|прихватило|прихватыва\w*|схватило|схватыва\w*|вступило|ноет\w*|зноби\w*|озноб\w*|морози\w*|беспоко\w*|давит\w*|ломит\w*|тян\w*|перш\w*|"
    r"залож\w*|онем\w*|тошн\w*|кашл\w*|урч\w*|стрел\w*|"
    r"щем\w*|гуд\w*|звен\w*|слез\w*|чеш\w*|горит|горят|сохн\w*|хруст\w*|"
    r"скрюч\w*|сводит|сводят|колотит\w*|рвет|рвёт|рвало|хрип\w*|дер[её]т|"
    r"шата\w*|неме\w*|дрож\w*|тряс[её]тся|трясутся|отек\w*|пухн\w*|темне\w*|мутн\w*|"
    r"задыха\w*|слабит|закрепило|частит|частят|скач\w*)$",
    re.I,
)
_SEVERITY = re.compile(
    r"\b(сильн\w*|терпим\w*|слаб\w*|невыносим\w*|ужасн\w*|пойд[её]т|сойд[её]т|"
    + "|".join(_yo_variants(SEVERITY_WORDS))
    + r")\b",
    re.I,
)
_TOLERANCE = re.compile(
    r"\b(?:(?:не\s+)?(?:могу|можно)\s+терпеть|терпеть\s+(?:не\s+)?могу)\b", re.I,
)


def tolerance_severity_spans(text: str) -> tuple[SemanticSpan, ...]:
    """Endurance answers with a closed complement, not tolerance of people/noise."""
    allowed = {"я", "это", "боль", "пока", "ещё", "еще", "уже", "ну", "да", "вполне"}
    result = []
    clauses = clause_bounds(text)
    for index, (start, _end, clause) in enumerate(clauses):
        if index and re.fullmatch(
            r"(?:я\s+)?(?:не\s+знаю|не\s+помню|не\s+уверен[а]?)", clauses[index - 1][2], re.I,
        ):
            continue
        for match in _TOLERANCE.finditer(clause):
            rest = clause[:match.start()] + " " + clause[match.end():]
            if not all(token.lower() in allowed for token in _TOKEN.findall(rest)):
                continue
            quote = match.group(0)
            result.append(SemanticSpan(
                span_id=_sid(), type=SpanType.SEVERITY, text=quote,
                start=start + match.start(), end=start + match.end(),
                normalized="сильно" if re.search(r"\bне\b", quote, re.I) else "терпимо",
                confidence=0.9,
            ))
    return tuple(result)
_STATUS = re.compile(
    r"\b(прошл\w*|лучше|получше|нормально|уже\s+не\s+бол\w*|не\s+болит|"
    r"почти\s+не\s+бол\w*|залечил\w*|выздоров\w*)\b",
    re.I,
)
_NEGATION = re.compile(r"\b(не|ни)\b", re.I)
_UNCERTAINTY = re.compile(r"\b(наверное|вроде|кажется|может\s+быть)\b", re.I)
_ISSUE_PHRASE = re.compile(
    r"([а-яё\-]+(?:\s+[а-яё\-]+){0,2})\s+"
    r"(бол(?!ее(?:\b|-))\w*|приболел\w*|заболел\w*|разболел\w*|поболел\w*|побалива\w*|поныва\w*|прихватило|прихватыва\w*|схватило|схватыва\w*|вступило|ноет\w*|зноби\w*|озноб\w*|морози\w*|беспоко\w*|давит\w*|ломит\w*|тян\w*|перш\w*|"
    r"залож\w*|онем\w*|тошн\w*|кашл\w*|урч\w*|стрел\w*)",
    re.I,
)
_ISSUE_BEFORE_BODY = re.compile(
    r"(бол(?!ее(?:\b|-))\w*|приболел\w*|заболел\w*|разболел\w*|поболел\w*|побалива\w*|поныва\w*|прихватило|прихватыва\w*|схватило|схватыва\w*|вступило|ноет\w*|зноби\w*|озноб\w*|морози\w*|онем\w*|перш\w*|залож\w*|тян\w*|ломит\w*|давит\w*)\s+"
    r"(?:в|на|у)\s+([а-яё\-]+)",
    re.I,
)
# Vital-sign conditions without a verb («давление высокое», «температура»):
# invisible otherwise (live: lone pressure complaints dropped entirely).
# Extended from SENSATION_NOUNS — same mechanism, one source of truth.
# Excluded from the bare trigger: шум/звон/туман need a body site («шум в
# ушах», «туман перед глазами») because bare «шум» is TV noise; жар is out
# entirely («на улице жара» vs «у меня жар» — температура covers fever).
_SENSATION_BARE = frozenset(
    w
    for w in SENSATION_NOUNS
    if w not in {"шум", "звон", "туман", "жар", "дрожь"}
)


_SENSATION_ALT = "|".join(sorted(_SENSATION_BARE, key=len, reverse=True))
_CONDITION = re.compile(
    r"\b(давление|давленьице|пульс|сахар|температура|температурка|"
    r"дрож[ьи]\b|" + _SENSATION_ALT + r")\w*",
    re.I,
)
# «сдавала кровь на анализ» is a lab procedure, not a complaint — the bare
# кровь trigger must not fire there («кровь из носа» still fires).
_LAB_BLOOD = re.compile(r"\bсдава\w*|\bсдать\b|\bанализ\w*", re.I)
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
    if lemma.replace("ё", "е") in BODY_SITE_LEMMAS:
        return lemma.replace("ё", "е")
    # Inflection is handled by morphology. Shared spelling is not anatomical
    # evidence: «ключи» must not become «ключица» through a four-letter prefix.
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
    # A different verb with the same prefix is still a different meaning:
    # «потеряла ключи» is not sweating. Use lemma or the explicit surface
    # grammar above, never a prefix plus a generic VERB tag.
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


def _pair_sensation_predicate(acc: _ParseAcc, clause: str, cstart: int) -> None:
    """One anatomical subject plus its nominal sensation predicate.

    A second entity/action is not ellipsis. Keep the person's adjective and
    quote; do not turn heaviness into pain or assign a severity/diagnosis.
    """
    tokens = list(_TOKEN.finditer(clause))
    bodies = [token for token in tokens if _body_site_from_token(token.group())]
    predicates = [token for token in tokens
                  if normalize_token(token.group()) in SENSATION_ADJECTIVES]
    if len(bodies) != 1 or len(predicates) != 1:
        return
    body, predicate = bodies[0], predicates[0]
    allowed = {"я", "у", "меня", "мне", "в", "на", "с", "со", "быть", "стать",
               "какой-то", "какой", "то", "это", "уже", "ещё", "тоже", "прямо", "немного"}
    for token in tokens:
        if token is body or token is predicate:
            continue
        if any(span.type in {SpanType.TIME, SpanType.DURATION}
               and span.start <= cstart + token.start() < span.end for span in acc.spans):
            continue
        if normalize_token(token.group()) not in allowed:
            return
    acc.add(SpanType.ISSUE, predicate.group(), cstart + predicate.start(),
            cstart + predicate.end(), 0.86)
    acc.add(SpanType.BODY_SITE, body.group(), cstart + body.start(), cstart + body.end(), 0.88)


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
    acc.spans.extend(tolerance_severity_spans(raw))
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
        _pair_sensation_predicate(acc, clause, cstart)

        for m in _CONDITION.finditer(clause):
            ctext, cstart_m, cend_m = (
                m.group(0),
                cstart + m.start(),
                cstart + m.end(),
            )
            if not any(
                s.type == SpanType.ISSUE and s.start <= cstart_m < s.end
                for s in acc.spans
            ):
                # The bare «боль» stem reintroduces the «больше» trap
                # (больше/большой/больница/болезнь are never symptoms alone).
                # Compare raw AND normalized: «больнице» normalizes to
                # «больница», «больше» to «большой».
                _ctext_low = ctext.lower()
                if _ctext_low in _FALSE_ISSUE_TOKENS:
                    continue
                if normalize_token(_ctext_low) in _FALSE_ISSUE_TOKENS:
                    continue
                if _LAB_BLOOD.search(clause) and "кров" in ctext.lower():
                    continue
                acc.add(SpanType.ISSUE, ctext, cstart_m, cend_m, 0.86)

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
