"""Literal issue-mention extraction from user text — evidence spans, no diagnosis."""

from __future__ import annotations

import re
import uuid

from packages.contracts.semantic import Evidence, FactCandidate, IssueMention

_BARE_SITE_RE = None


def _bare_site_clause_re() -> re.Pattern[str]:
    """Bare-site clause matcher; lexicon lemmas appended lazily to avoid a
    circular import (semantic_kernel/__init__ imports kernel → this module)."""
    global _BARE_SITE_RE
    if _BARE_SITE_RE is None:
        from packages.dialogue_engine.semantic_kernel.lexicon import (
            BODY_SITE_LEMMAS,
        )

        _BARE_SITE_RE = re.compile(
            r"^(?:и|а|но|вот|у\s+меня|меня)?\s*(?:ещ[её]\s+)?"
            r"(голова|живот|спина|нога|ноги|рука|руки|грудь|шея|поясница|колено|горло|"
            + "|".join(sorted(BODY_SITE_LEMMAS))
            + r")"
            r"(?:\s+(?:тоже|также))?\s*$",
            re.I,
        )
    return _BARE_SITE_RE


def _normalize_site_token(token: str) -> str:
    from packages.dialogue_engine.semantic_kernel.morphology import (
        normalize_token,
    )

    return normalize_token(token)


def _site_in_lexicon(site: str) -> bool:
    from packages.dialogue_engine.semantic_kernel.lexicon import (
        BODY_SITE_LEMMAS,
    )

    return site in BODY_SITE_LEMMAS


def _cap_site(token: str) -> str:
    token = (token or "").strip()
    return token[0].upper() + token[1:] if token else token

_PAIN_VERB = re.compile(
    r"\b(бол(?!ее(?:\b|-))\w*|зноби\w*|озноб\w*|морози\w*|приболел\w*|заболел\w*|разболел\w*|поболел\w*|"
    r"побал\w*|побалива\w*|поныва\w*|ноет\w*|беспоко\w*|давит\w*|ломит\w*|"
    r"прихватило|схватило|вступило)\b",
    re.I,
)
_CORRECTION = re.compile(
    r"\b(я\s+же\s+говорил\w*|говорил\w*\s+же|"
    r"(?:нет,?\s+)?я\s+про\s+(?:мужа|жену|сына|дочь|мать|отца|соседа|соседку)|"
    r"это\s+у\s+(?:мужа|жены|сына|дочери|матери|отца|соседа|соседки)|"
    r"не\s+у\s+меня|не\s+я\s+болею)\b",
    re.I,
)
_REPAIR_HEARING = re.compile(r"\b(алло|слыш\w*|повтор\w*)\b", re.I)
_USER_QUESTION = re.compile(
    r"(кто\s+вы|(?:к|х)то\s+(это|там|звонит|такая|такой)|зачем\s+звон|почему\s+звон|"
    r"что\s+вам\s+нужн|а\s+вы\s+кто|"
    r"что\s+вы\s+хотите|зачем\s+вы|про\s+что|"
    r"что\s+ты\s+спрашивал\w*|что\s+вы\s+спрашивали|"
    r"о\s+ч[её]м\s+ты\s+спрашивал\w*|что\s+ты\s+сейчас\s+спросил\w*|"
    r"не\s+знаю\s+(?:вас|тебя)|(?:вас|тебя)\s+не\s+знаю)",
    re.I,
)
_ONSET = re.compile(
    r"\b(с\s+утра|с\s+десяти|с\s+10|вчера|сегодня|давно|"
    r"час\w*|утр\w*|дн\w*|недел\w*|месяц\w*)\b",
    re.I,
)
_SEVERITY = re.compile(r"\b(сильн\w*|терпим\w*|слаб\w*|невыносим\w*|пойд[её]т|сойд[её]т)\b", re.I)
_IMPROVING = re.compile(r"\b(почти\s+не\s+бол\w*|уже\s+почти|легче|лучше|прошл\w*)\b", re.I)
_RESOLVED = re.compile(r"\b(не\s+болит|уже\s+не\s+бол\w*|прошл\w*)\b", re.I)


def _evidence(raw: str, start: int, end: int) -> Evidence:
    quote = raw[start:end]
    return Evidence(start=start, end=end, quote=quote)


def _mid() -> str:
    return f"im-{uuid.uuid4().hex[:8]}"


def _split_symptom_parts(text: str) -> list[str]:
    parts = re.split(r"\s*[,;]\s*|\s*[\.…!?]+\s*", text.strip())
    out: list[str] = []
    for part in parts:
        sub = re.split(r"\s+и\s+", part.strip())
        out.extend(s.strip() for s in sub if s.strip())
    return out or [text.strip()]


_BARE_SITE_CLAUSE = None  # built lazily via _bare_site_clause_re()
# Bare-site correction pivot («Ой, нет, голова.», «Не живот, а голова.»):
# the denied site never matches _BARE_SITE_CLAUSE (its «не» prefix is not an
# allowed prefix), so only the corrected site grounds a mention.
_BARE_CORRECTION_PIVOT = re.compile(r"\bнет\b|\bне\s+[а-яё]+,?\s+а\b", re.I)
# Sensation + location without a pain verb («тяжесть в животе», «шум в
# ушах»). The site requirement is structural: bare «шум» is TV noise,
# bare «туман» is weather — only the paired form is a complaint.
_SENSATION_SITE = re.compile(
    r"\b(тяжесть|тяжести|жжение|жжения|резь|рези|ломота|ломоты|колик\w*|"
    r"спазм\w*|судорог\w*|онемение|онемения|покалывание|зуд|дрожь|озноб\w*|"
    r"потливость|слабость|усталость|одышк\w*|удушье|сердцебиение|от[её]к\w*|"
    r"мокрот\w*|лихорад\w*|"
    r"синяк\w*|сыпь|головокружение|тошнот\w*|рвот\w*|каш\w*|насморк\w*|"
    r"чихан\w*|икот\w*|отрыжк\w*|изжог\w*|запор\w*|понос\w*|гной\w*|"
    r"сухость|першение|горечь|жажд\w*|бол[ьи]\w*|кров[ьи]\w*)\b"
    r"\s+(в|на|у|во|из|ис|с|со|от|до|под|над|к|ко|за|внизу|внутри)\s+"
    r"([а-яё\-]+(?:\s+[а-яё\-]+){0,2})",
    re.I,
)
# Function loss: the part stopped working («заклинило», «не
# поднимается»). Paired with a site in the clause; bare «не могу» alone
# is not a complaint (could be the phone, the door, anything).
_FUNCTION_LOSS = re.compile(
    r"\b(заклинило|заклинивает|отнима\w*|отнял\w*|не\s+"
    r"(?:поднимается|поднимаются|разгибается|сгибается|держит|держат|"
    r"слушается|слушаются|двигается|двигаются|гнутся|шевелится))\b",
    re.I,
)


def _find_clause_site(lower_clause: str) -> tuple[str, str]:
    """First lexicon site in the clause → (lemma, raw token)."""
    for _tok in re.findall(r"[а-яё\-]{3,}", lower_clause):
        _norm = _normalize_site_token(_tok)
        if _site_in_lexicon(_norm):
            return _norm, _tok
    return "", ""


# Vital-sign complaints. Bare давление/температура name the complaint;
# пульс/сахар need a qualifier (else «мерила сахар» — a procedure).
_VITALS_PROCEDURE = re.compile(
    r"\b(мерил\w*|измер\w*|померил\w*|сдава\w*|сдать|анализ\w*)\b",
    re.I,
)
_VITALS_BAD_QUALIFIER = re.compile(
    r"\b(скач\w*|высок\w*|низк\w*|поднял\w*|упал\w*|зашкали\w*|"
    r"частит|частят|замира\w*|колотит\w*|стучит)\b",
    re.I,
)
# «Давление нормальное» reports no complaint — an ok-qualifier without
# a bad one silences the vitals rule (live contract).
_VITALS_OK_QUALIFIER = re.compile(
    r"\b(нормальн\w*|в\s+норме|хорош\w*|обычн\w*|стабильн\w*|"
    r"как\s+всегда|как\s+обычно)\b",
    re.I,
)
_VITALS_COMPLAINT = re.compile(
    r"\b(давление|давленьице|температура|температурка)\b"
    r"|\b(пульс|сахар)\b\s*(?:\s+\w+){0,2}?\s*"
    r"(скач\w*|высок\w*|низк\w*|поднял\w*|упал\w*|зашкали\w*|"
    r"частит|частят|замира\w*|колотит\w*|стучит)\b"
    r"|\b(давление|температура|пульс)\s+(скачет|высокое|низкое|поднялось|упало)\b",
    re.I,
)


def _vital_label(m: re.Match[str]) -> str:
    for _g in m.groups():
        if _g:
            return _g.strip()
    return "давление"


# Bare systemic complaints: the elder naming it is the complaint, no
# site possible («неможется», «расхворалась», «мокрота», «закрепило»).
# Deliberately NOT hunger/thirst/appetite or mood words — those belong
# to the wellness/background paths, and NOT bare pain verbs (covered).
_BARE_SYSTEMIC = re.compile(
    r"\b(неможется|не\s+можется|расхвор\w*|хвора\w*|хворь|"
    r"лихорад\w*|лихорадка|мокрот\w*|изжог\w*|одыш\w*|удушье|"
    r"головокруж\w*|тошнот\w*|рвот\w*|запор\w*|понос\w*|"
    r"насморк\w*|чихан\w*|отрыжк\w*|икот\w*|сердцебиение|"
    r"каш\w*|слабост\w*|потливост\w*|мути\w*)\b",
    re.I,
)
_SENSATION_EAR_NOISE = re.compile(
    r"\b(шум|звон)\b\s+(в)\s+(ушах|ухе|голове)\b",
    re.I,
)
_SENSATION_EYE_FOG = re.compile(
    r"\b(туман|двоение|двоится)\b\s+(в|перед)\s+(глазах|глазами|глазу)\b",
    re.I,
)


def _clause_mentions(
    raw: str, clause: str, *, first_symptom: bool, shared_verb: bool = False
) -> list[IssueMention]:
    n = clause.lower()
    mentions: list[IssueMention] = []
    base = raw.lower().find(n)
    if base < 0:
        base = 0

    def add(
        *,
        label: str,
        kind: str,
        body_site: str | None,
        role: str,
        quote: str,
    ) -> None:
        from packages.dialogue_engine.semantic_kernel.morphology import normalize_text

        start = raw.lower().find(quote.lower())
        if start < 0:
            start = base
        end = min(len(raw), start + len(quote))
        mentions.append(
            IssueMention(
                mention_id=_mid(),
                kind=kind,
                label=label,
                canonical_key=normalize_text(label),
                role=role,
                body_site=body_site,
                temporal_scope="now",
                status=_status_from_clause(n),
                onset=_onset_from_clause(n),
                severity=_severity_from_clause(n),
                evidence=_evidence(raw, start, end),
            )
        )

    if re.search(r"голов\w*", n) and (_PAIN_VERB.search(n) or shared_verb):
        add(
            label="головная боль",
            kind="symptom",
            body_site="голова",
            role="primary" if first_symptom else "independent",
            quote=clause,
        )
        first_symptom = False
    if re.search(r"\bтошн\w*\b", n) and "живот" not in n:
        add(
            label="тошнота",
            kind="symptom",
            body_site=None,
            role="associated" if mentions else "primary",
            quote=clause,
        )
    if re.search(r"\bживот\w*\b", n) and (_PAIN_VERB.search(n) or shared_verb):
        add(
            label="боль в животе",
            kind="symptom",
            body_site="живот",
            role="primary" if first_symptom else "independent",
            quote=clause,
        )
        first_symptom = False
    if re.search(r"\b(жоп\w*|ягодиц\w*|поп\w*)\b", n) and (
        _PAIN_VERB.search(n) or shared_verb
    ):
        add(
            label="боль в ягодицах",
            kind="symptom",
            body_site="ягодицы",
            role="primary" if first_symptom else "independent",
            quote=clause,
        )
        first_symptom = False
    if re.search(r"\bтел\w*\b", n) and _PAIN_VERB.search(n):
        add(
            label="ломота в теле",
            kind="symptom",
            body_site="тело",
            role="primary" if first_symptom else "independent",
            quote=clause,
        )
        first_symptom = False
    # A fall is a functional event, not a pain verb — but for elderly care
    # it must ground an episode (onset/current probes come free) instead of
    # vanishing into a generic question. Negated falls («не падала») are
    # not events. Other-person falls never reach here (suppressed above).
    if re.search(r"\bупал[аио]?\b|\bпадени[ея]\b", n) and not re.search(
        r"\bне\s+(?:упал[аио]?|падал[аио]?)\b", n
    ):
        add(
            label="падение",
            kind="function_issue",
            body_site=None,
            role="primary" if first_symptom else "independent",
            quote=clause,
        )
        first_symptom = False
    # Whole-body pain («Всё болит.») is a site-less complaint that must not
    # vanish: record it on the body. The generic rule below excludes
    # всё/все deliberately (they are not sites), so this needs its own rule.
    if re.search(r"\bвс[её]\b", n) and _PAIN_VERB.search(n):
        add(
            label="всё болит",
            kind="symptom",
            body_site="тело",
            role="primary" if first_symptom else "independent",
            quote=clause,
        )
        first_symptom = False
    if re.search(r"\bплохо\s+спал\w*\b|\bне\s+спал\w*\b|\bбессон\w*\b", n):
        add(
            label="плохой сон",
            kind="sleep_problem",
            body_site=None,
            role="primary" if first_symptom else "independent",
            quote=clause,
        )

    # Sensation + location without a pain verb («тяжесть в животе»).
    # Runs before the generic fallback so the label is a speakable noun
    # phrase, not a bare noun. The site token is resolved through the
    # morphology layer; an unresolvable site means no mention.
    if not any(m.role in ("primary", "independent") for m in mentions):
        for _sens_re, _kind in (
            (_SENSATION_SITE, "symptom"),
            (_SENSATION_EAR_NOISE, "symptom"),
            (_SENSATION_EYE_FOG, "symptom"),
        ):
            _sm = _sens_re.search(n)
            if not _sm:
                continue
            _site = ""
            _site_tok = ""
            for _cand in _sm.group(3).strip().split():
                _cand = _cand.strip()
                if not _cand:
                    continue
                _resolved = _normalize_site_token(_cand)
                if _cand.lower() in ("ушах", "ухе"):
                    _resolved = "ухо"
                elif _cand.lower() in ("глазах", "глазами", "глазу"):
                    _resolved = "глаз"
                elif _cand.lower() in ("голове",):
                    _resolved = "голова"
                if _site_in_lexicon(_resolved):
                    _site, _site_tok = _resolved, _cand
                    break
            if not _site:
                continue
            _sens = _sm.group(1).strip()
            _prep = _sm.group(2).strip()
            add(
                label=f"{_sens} {_prep} {_site_tok}",
                kind=_kind,
                body_site=_site,
                role="primary" if first_symptom else "independent",
                quote=clause,
            )
            first_symptom = False
            break

    # Bare site sharing the turn's pain verb («Болит голова и нога») or named
    # as a correction («Нет, нога.»). The specific rules above only know a
    # handful of sites; every other site was silently lost here. No
    # already-mentioned guard: a bare-site match implies no specific rule
    # fired on this part (they all need verbs), so duplicates are
    # impossible by construction — unlike the generic rule below.
    if shared_verb:
        _bm = _bare_site_clause_re().match(n.rstrip(".,!?…"))
        if _bm:
            _btok = _bm.group(1).strip()
            _bnorm = _normalize_site_token(_btok)
            _bsite = _bnorm if _site_in_lexicon(_bnorm) else _btok.lower()
            add(
                label=f"{_cap_site(_btok)} {_agree_verb(_btok)}",
                kind="symptom",
                body_site=_bsite,
                role="primary" if first_symptom else "independent",
                quote=clause,
            )
            first_symptom = False

    # Generic construction fallback: ANY noun + pain verb is a body site.
    # The specific rules above keep their canonical labels; this only runs
    # when a clause produced no mention, so it closes the whole class of
    # holes (зуб, спина, нога, горло, ухо, ребро, ...) without a body-part
    # list. Live fs-4d8f5a8b: «Начал зук болит у меня.» extracted NOTHING and
    # the freshest symptom was lost at summary.
    if not mentions or not any(m.role in ("primary", "independent") for m in mentions):
        for g in _GENERIC_BODY_PAIN.finditer(n):
            site = (g.group(1) or "").strip()
            verb_first = not site
            if verb_first:
                # Verb-first order («Сломала руку», «Болит нога»): the noun
                # must resolve to a known site — no raw fallback, an
                # unresolved noun here is usually an adverbial («болит,
                # наверное»).
                site = (g.group(2) or "").strip()
                if not site or _NON_BODY_NOUN.search(site):
                    continue
                _norm = _normalize_site_token(site)
                if not _site_in_lexicon(_norm):
                    continue
                site, _body = site, _norm
            else:
                if not site or _NON_BODY_NOUN.search(site):
                    continue
                # Normalize long sites to the lemma («Руке» → «рука»); keep short
                # or unknown words raw — morphology maps «Пах» → «пахнуть» and
                # «Зук» must stay the elder's own word.
                _norm = _normalize_site_token(site)
                _body = (
                    _norm
                    if len(site) >= 4 and _site_in_lexicon(_norm)
                    else site.lower()
                )
            add(
                label=f"{site} {_agree_verb(site)}",
                kind="symptom",
                body_site=_body,
                role="primary" if first_symptom else "independent",
                quote=clause,
            )
            first_symptom = False
            break

    # Function loss without a pain verb («шею заклинило», «плечо не
    # поднимается»): a known site + a loss predicate in the same clause.
    # Runs when nothing fired yet, so no duplicates by construction.
    if not mentions or not any(m.role in ("primary", "independent") for m in mentions):
        _loss = _FUNCTION_LOSS.search(n)
        if _loss:
            _lsite, _lraw = _find_clause_site(n)
            if _lsite:
                _verb = _loss.group(0).strip()
                add(
                    label=f"{_lsite} {_verb}",
                    kind="symptom",
                    body_site=_lsite,
                    role="primary" if first_symptom else "independent",
                    quote=clause,
                )
                first_symptom = False

    # Vital signs («давление скачет», bare «давление»): invisible
    # otherwise. Procedures («мерила сахар», «сдала кровь») never fire —
    # measuring is not complaining.
    if not mentions or not any(m.role in ("primary", "independent") for m in mentions):
        if not _VITALS_PROCEDURE.search(n) and not (
            _VITALS_OK_QUALIFIER.search(n)
            and not _VITALS_BAD_QUALIFIER.search(n)
        ):
            _vit = _VITALS_COMPLAINT.search(n)
            if _vit:
                add(
                    label=_cap_site(_vital_label(_vit)),
                    kind="symptom",
                    body_site=None,
                    role="primary" if first_symptom else "independent",
                    quote=clause,
                )
                first_symptom = False

    # Bare systemic complaints («неможется», «мокрота», «закрепило»):
    # no site, no verb pair — but an elder naming it IS the complaint.
    # Last resort only; questions and already-covered clauses never reach
    # here with empty mentions... except truly empty ones, hence the
    # explicit guards: no '?', no user-question/repair markers.
    if not mentions:
        if "?" not in clause and not _REPAIR_HEARING.search(n):
            _bare = _BARE_SYSTEMIC.search(n)
            if _bare:
                add(
                    label=_cap_site(_bare.group(0).strip()),
                    kind="symptom",
                    body_site=None,
                    role="primary" if first_symptom else "independent",
                    quote=clause,
                )
                first_symptom = False
    return mentions


def _status_from_clause(n: str) -> str:
    if _RESOLVED.search(n):
        return "resolved"
    if _IMPROVING.search(n):
        return "improving"
    return "active"


def _onset_from_clause(n: str) -> str | None:
    m = _ONSET.search(n)
    return m.group(0) if m else None


def _severity_from_clause(n: str) -> str | None:
    m = _SEVERITY.search(n)
    return m.group(0) if m else None


_CLAUSE_SPLIT_RE = re.compile(
    r"\s*[,;]\s*|\s+(?:а|но|однако)\s+|[.…!?]+\s*",
    re.I,
)
def _agree_verb(site_tok: str) -> str:
    """Number agreement for generic labels («суставы болят», «спина болит»).

    A noun directly before a pain verb is the nominative subject in 99% of
    cases, so plural endings mean plural pain. Explicit set covers «глаза»;
    genitive-singular collision («боль руки») is negligible here.
    """
    low = (site_tok or "").lower()
    if low in ("глаза", "уши", "зубы", "ноги", "руки", "плечи", "колени"):
        return "болят"
    if len(low) > 3 and low.endswith(("ы", "и")):
        return "болят"
    return "болит"


_GENERIC_BODY_PAIN = re.compile(
    r"\b([а-яё]{3,})\b"
    r"(?:\s+(?:сильно|очень|немного|чуть|ещ[её]|тоже|постоянно|давно|"
    r"невыносимо|нестерпимо|страшно))?"
    r"\s+(?:болит|болит[аиуы]?|ноет|ноют|ломит|ломит[аи]?|давит|стреляет|"
    r"стрелял|жж[её]т|жг[её]т|пульсирует|колет|першит|першило|"
    r"залож\w*|онем\w*|тошн\w*|кашл\w*|тян\w*|урч\w*|"
    r"крут\w*|выкруч\w*|слом\w*|"
    # Elder-speech verbs (battery 2026-09-30): explicit forms where a
    # stem collides (горит/говорит, печёт/печень, частит/часто).
    r"щем\w*|гуд\w*|звен\w*|слез\w*|чеш\w*|горит|горят|сохн\w*|"
    r"хруст\w*|скрюч\w*|сводит|сводят|колотит\w*|рвет|рвёт|рвало|"
    r"хрип\w*|дер[её]т|дерут|шата\w*|подкашив\w*|неме\w*|дрож\w*|"
    r"отек\w*|опух\w*|пухн\w*|темне\w*|мутн\w*|поте\w*|задыха\w*|"
    r"закрепило|слабит|частит|частят|замира\w*|стучит|скач\w*|"
    r"печет|печёт|мути\w*)\b"
    r"|\b(?:болит|болит[аиуы]?|ноет|ноют|ломит|давит|тянет|крутит|"
    r"заложило|онемело|тошнит|кашляет|першит|сломал\w*|выкруч\w*|урчит|"
    r"щемит|гудит|звенит|слезятся|чешется|горит|сохнет|хрустит|"
    r"скрючивает|сводит|колотится|рвёт|хрипит|дерёт|шатает|немеют|"
    r"дрожат|отекают|темнеет|потею|задыхаюсь|частит|замирает|скачет)\b"
    r"\s+([а-яё]{3,})\b",
    re.I,
)
# Words that are not a body site even in "<noun> болит" position.
_NON_BODY_NOUN = re.compile(
    r"^(?:не|ни|мне|меня|я|он|она|оно|они|нас|вас|все|всё|всего|кто|что|"
    r"очень|сильно|немного|ещё|еще|тоже|тоже|плохо|хорошо|само|сама|ещё)$",
    re.I,
)


def extract_issue_mentions(text: str) -> tuple[IssueMention, ...]:
    """Extract literal issue mentions with evidence — never infer unstated body sites."""
    raw = text.strip()
    if not raw:
        return ()
    from packages.dialogue_engine.check_path import (
        is_other_person_health_frame,
        suppress_health_issues_for_non_complaint_frame,
    )
    from packages.dialogue_engine.semantic_kernel.lexicon import has_other_person

    # False-world frames (dream/film, other-person, joke, past-resolved):
    # never speaker ISSUE_SITE (map docs/plans/Understand-false-worlds.md).
    # Other-person suppression is clause-local: a speaker complaint in
    # another clause voids it («Живот болит. Внук приезжал. А ещё спина.»).
    # Dream/joke/past suppression stays whole-text.
    if suppress_health_issues_for_non_complaint_frame(raw):
        if not (
            _CLAUSE_SPLIT_RE.search(raw)
            and has_other_person(raw)
            and is_other_person_health_frame(raw)
        ):
            return ()
        _parts = _CLAUSE_SPLIT_RE.split(raw)
        _kept = [
            p.strip()
            for p in _parts
            if p.strip() and not is_other_person_health_frame(p.strip())
        ]
        if not _kept:
            return ()
        raw = ". ".join(_kept).strip()
        raw = re.sub(r"^(?:а|но|однако)\s+", "", raw, flags=re.I).strip()
        if not raw:
            return ()

    parts = _split_symptom_parts(raw)
    all_mentions: list[IssueMention] = []
    shared_verb = any(bool(_PAIN_VERB.search(p.lower())) for p in parts)
    correction_pivot = bool(_BARE_CORRECTION_PIVOT.search(raw))
    first = True
    for part in parts:
        bare_site = (shared_verb or correction_pivot) and bool(
            _bare_site_clause_re().match(part.strip().lower().rstrip(".,!?…"))
        )
        found = _clause_mentions(
            raw, part, first_symptom=first, shared_verb=bare_site
        )
        if found and all_mentions:
            adjusted: list[IssueMention] = []
            for m in found:
                if m.label == "тошнота":
                    adjusted.append(m.model_copy(update={"role": "associated"}))
                elif m.role == "primary":
                    adjusted.append(m.model_copy(update={"role": "independent"}))
                else:
                    adjusted.append(m)
            found = adjusted
        if found:
            all_mentions.extend(found)
            first = False
    if len(all_mentions) == 1 and all_mentions[0].role == "unknown":
        all_mentions[0] = all_mentions[0].model_copy(update={"role": "primary"})
    return tuple(all_mentions)


_WELLNESS_FREE_POSITIVE = re.compile(
    r"(?:\bвс[её]\s+(?:хорошо|нормально|отлично|прекрасно|замечательно)\b|"
    r"\b(?:хорошо|нормально|отлично|великолепн\w*|прекрасно|замечательно|"
    r"великолепно)\b)",
    re.I,
)
_WELLNESS_FREE_NEGATED_POSITIVE = re.compile(
    r"\bне\s+(?:очень\s+)?(?:хорош\w*|нормальн\w*|отличн\w*|прекрасн\w*)",
    re.I,
)
_WELLNESS_CRISIS = re.compile(
    r"\b(умира\w*|умираю|помогите|спасите|скор\w*|плохо\s+мне|мне\s+плохо)\b",
    re.I,
)


_TRAILING_POSITIVE = re.compile(
    r"(хорошо|отлично|нормально|прекрасно|замечательно|супер)\s*[.!?…]*$",
    re.I,
)


def _pain_only_negated(judged_lower: str) -> bool:
    """True when pain markers exist only under negation and no non-pain
    negative marker fired ("Не болит ничего" vs "плохо"). Requires an
    explicit negator — bare "устал" stays negative."""
    from packages.dialogue_engine.check_path import complaint_without_negation

    if complaint_without_negation(judged_lower):
        return False
    if not re.search(r"\b(не|нет|ничего|никак)\b", judged_lower):
        return False
    pain_present = bool(
        re.search(
            r"(бол|тошн|кружи|дурно|мутит|тяжел|температур|слабость|"
            r"ноет|ломит|давит|тошнит|знобит|озноб|беспокоит|тревожит|"
            r"устал|слаб)",
            judged_lower,
        )
    )
    if not pain_present:
        return False
    nonpain_neg = bool(
        re.search(
            r"(мне\s+плохо|плохо\s+мне|(?<!не\s)\bплохо\b|плохо\s+себя|"
            r"самочувствие\s+(плохое|плохо|неважное)|"
            r"умира|ужасн|отвратительн|паршив|хреново|фигово|дерьмово|гнусно|мерзко|"
            r"погано|кошмарно|грустно|не\s+очень|нехорошо|состояние\s+не)",
            judged_lower,
        )
    )
    return not nonpain_neg


def _denied_pain_with_positive(text: str) -> bool:
    """Denied pain + positive summary ("Ничего не болит, всё хорошо").

    No unnegated complaint anywhere, and the last clause is positive.
    "Голова болит, но в целом нормально" stays negative (real complaint).
    """
    from packages.dialogue_engine.check_path import complaint_without_negation

    lowered = (text or "").lower().replace("ё", "е")
    if complaint_without_negation(lowered):
        return False
    return bool(_TRAILING_POSITIVE.search(lowered))


def extract_goal_facts(
    text: str,
    *,
    answer_slot: str | None = None,
) -> tuple[FactCandidate, ...]:
    """Harvest all check-slot facts visible in free speech (any order).

    answer_slot is a hint, not a gate — one utterance may cover wellness+mood+plans.
    """
    raw = text.strip()
    if not raw:
        return ()
    n = raw.lower().replace("ё", "е")
    # Subject guard: someone else's complaint («у мужа голова болит») yields
    # NO speaker facts — not wellness, mood, or sleep (reviewer item 2).
    # Mixed turns («а у меня живот») carry speaker markers and proceed.
    from packages.dialogue_engine.semantic_kernel.lexicon import (
        OTHER_PERSON_MARKERS,
    )

    _low = n
    _has_other = any(m in _low for m in OTHER_PERSON_MARKERS)
    _has_speaker = bool(
        re.search(r"\b(я|мне|меня|мной|у\s+меня|мною|сам|сама)\b", _low)
    )
    if _has_other and not _has_speaker:
        return ()
    if _has_other and _has_speaker:
        # Mixed subjects («у мужа плохо, а у меня более-менее»): evaluate
        # speaker clauses only — husband's «плохо» must not become speaker
        # wellness. Drop other-only clauses, keep speaker evidence.
        try:
            from packages.dialogue_engine.policy import (
                _is_other_person_only as _mixed_other_only,
            )

            _parts = re.split(r"\s*[,;]\s*|\s+а\s+|\s+но\s+|\s+однако\s+", raw)
            _kept = [
                p.strip()
                for p in _parts
                if p.strip() and not _mixed_other_only(p.strip())
            ]
            if not _kept:
                return ()
            raw = " ".join(_kept).strip()
            raw = re.sub(r"^а\s+", "", raw, flags=re.I).strip()
            n = raw.lower().replace("ё", "е")
            _low = n
        except Exception:  # noqa: BLE001
            pass
    facts: list[FactCandidate] = []
    full_evidence = _evidence(raw, 0, len(raw))
    seen: set[str] = set()

    from packages.dialogue_engine.fast_interpreter import (
        _MOOD_NEGATIVE,
        _MOOD_NEGATIVE_PHRASE,
        _MOOD_POSITIVE,
        _NEGATIVE,
        _NORMAL,
        _PLANS_ANSWER,
        _POSITIVE,
        _SLEEP_ANSWER,
        _SO_SO,
        _WELLNESS_NEGATIVE,
        _WELLNESS_POSITIVE,
        self_correction_tail,
    )
    from packages.dialogue_engine.fast_interpreter import (
        is_nonhealth_evaluation as _is_film_like,
    )

    core = re.sub(r"[.!?…]+$", "", raw).strip()
    _tail = self_correction_tail(raw)
    _judge = _tail if _tail is not None else raw
    _judge_n = _judge.lower().replace("ё", "е")
    # «плохо спал» is sleep evidence, not a wellness crisis by itself
    _judge_wellness = re.sub(r"плох\w*\s+спал\w*", " ", _judge_n)

    def _add(field: str, value: str, *, start: int = 0, end: int | None = None) -> None:
        if field in seen:
            return
        seen.add(field)
        evidence = full_evidence if end is None else _evidence(raw, start, end)
        facts.append(
            FactCandidate(
                field=field,
                value=value,
                subject="speaker",
                temporal_scope="now",
                negated=False,
                evidence=evidence,
            )
        )

    wellness_neg = bool(
        not _is_film_like(raw)
        and (
            _WELLNESS_CRISIS.search(_judge_wellness)
            or _WELLNESS_NEGATIVE.search(_judge_wellness)
            or _WELLNESS_FREE_NEGATED_POSITIVE.search(_judge_wellness)
            or re.search(r"\b(не\s+очень|плох\w*|состояние\s+не|умира\w*)\b", _judge_wellness)
            or _NEGATIVE.match(core)
        )
    )
    if wellness_neg and _pain_only_negated(_judge_wellness):
        # Negated pain alone ("Не болит ничего") is not negative wellness —
        # it is the absence of complaint (live hard-battery). Non-pain
        # negatives (плохо/ужасно/не очень) still count.
        wellness_neg = False
    if wellness_neg and _denied_pain_with_positive(raw):
        # Human denied pain and summarized positive ("Ничего не болит,
        # всё хорошо") — that is positive, never negative (live fs-6e3abff0).
        wellness_neg = False
        wellness_pos = True
    else:
        wellness_pos = bool(
            not wellness_neg
            and (
                _WELLNESS_POSITIVE.search(_judge_n)
                or _POSITIVE.match(core)
                or _WELLNESS_FREE_POSITIVE.search(_judge_wellness)
                or _NORMAL.match(core)
            )
        )
    if wellness_neg:
        _add("wellness", "negative")
    elif wellness_pos:
        _add("wellness", "positive")
    elif answer_slot == "wellness" and (
        _POSITIVE.match(core)
        or _SO_SO.match(core)
        or re.search(
            r"(так\s+себе|более[\s\-‑—]*менее|сойд|пойд|терпимо)",
            _judge_n,
            re.I,
        )
    ):
        _is_soso = bool(
            _SO_SO.match(core)
            or re.search(
                r"(так\s+себе|более[\s\-‑—]*менее|сойд|пойд|терпимо|средн)",
                n,
                re.I,
            )
        )
        _add("wellness", "uncertain" if _is_soso else "positive")

    if (answer_slot == "mood" and _MOOD_NEGATIVE.match(core)) or (
        _MOOD_NEGATIVE_PHRASE.search(_judge_n)
    ):
        _add("mood", "negative")
    elif _MOOD_POSITIVE.search(_judge_n) or (
        re.search(r"настроени\w*", _judge_n)
        and re.search(r"\b(хорош\w*|нормальн\w*|отличн\w*|спокойн\w*)\b", _judge_n)
        and not _MOOD_NEGATIVE_PHRASE.search(_judge_n)
    ):
        _add("mood", "positive")
    elif answer_slot == "mood" and (
        _POSITIVE.match(core) or _SO_SO.match(core) or _NORMAL.match(core)
    ):
        _add("mood", "positive" if not _SO_SO.match(core) else "uncertain")

    if _SLEEP_ANSWER.search(n):
        _add("sleep", raw)

    if _PLANS_ANSWER.search(n):
        _add("plans", raw)

    # Opening «как себя чувствуете?» answered with mood/sleep still covers wellness entry.
    if (
        answer_slot == "wellness"
        and "wellness" not in seen
        and ("mood" in seen or "sleep" in seen)
    ):
        mood_fact = next((f for f in facts if f.field == "mood"), None)
        if mood_fact and mood_fact.value == "negative":
            _add("wellness", "negative")
        else:
            _add("wellness", "positive")

    return tuple(facts)


def detect_correction(text: str) -> bool:
    return bool(_CORRECTION.search(text))


def detect_user_question(text: str) -> str | None:
    if _REPAIR_HEARING.search(text):
        return None
    m = _USER_QUESTION.search(text)
    if not m:
        return None
    return text.strip()


_SYMPTOM_SIGNAL = re.compile(
    r"\b(бол(?!ее(?:\b|-))\w*|зноби\w*|озноб\w*|морози\w*|приболел\w*|заболел\w*|разболел\w*|поболел\w*|побалива\w*|поныва\w*|прихватило|прихватыва\w*|схватило|схватыва\w*|вступило|давит\w*|тяжел\w*|тошн\w*|одыш\w*|затрудн\w*|не\s+мог\w*)\b",
    re.I,
)


def _looks_symptomatic(clause: str) -> bool:
    return bool(_SYMPTOM_SIGNAL.search(clause.lower()))


def requires_rich_interpretation(text: str) -> bool:
    """Fast bypass forbidden for multi-symptom / correction / user-question turns."""
    raw = text.strip()
    if not raw:
        return False
    if detect_correction(raw) or detect_user_question(raw):
        return True
    mentions = extract_issue_mentions(raw)
    if len(mentions) >= 2:
        return True
    parts = _split_symptom_parts(raw)
    symptomatic_parts = [p for p in parts if _looks_symptomatic(p) or extract_issue_mentions(p)]
    if len(symptomatic_parts) >= 2:
        return True
    if re.search(r"голов\w*.*тошн|тошн.*голов", raw, re.I):
        return True
    return False


def should_use_rich_turn(
    text: str,
    answer_slot: str | None,
    *,
    is_topic_slot_fn,
    pending_episode_attribute: str | None = None,
) -> bool:
    if answer_slot and answer_slot.startswith("episode_"):
        return True
    if pending_episode_attribute:
        return True
    if detect_correction(text) or detect_user_question(text):
        return True
    return requires_rich_interpretation(text)
