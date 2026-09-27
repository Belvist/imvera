"""Literal issue-mention extraction from user text — evidence spans, no diagnosis."""

from __future__ import annotations

import re
import uuid

from packages.contracts.semantic import Evidence, FactCandidate, IssueMention

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
    r"(кто\s+вы|хто\s+(это|там|звонит)|зачем\s+звон|почему\s+звон|"
    r"что\s+вам\s+нужн|а\s+вы\s+кто|"
    r"что\s+вы\s+хотите|зачем\s+вы|про\s+что|"
    r"что\s+ты\s+спрашивал\w*|что\s+вы\s+спрашивали|"
    r"о\s+ч[её]м\s+ты\s+спрашивал\w*|что\s+ты\s+сейчас\s+спросил\w*)",
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
    parts = re.split(r"\s*,\s*|\s*;\s*", text.strip())
    out: list[str] = []
    for part in parts:
        sub = re.split(r"\s+и\s+", part.strip())
        out.extend(s.strip() for s in sub if s.strip())
    return out or [text.strip()]


_BARE_SITE_CLAUSE = re.compile(
    r"^(?:и|а|но|вот|у\s+меня|меня)?\s*"
    r"(голова|живот|спина|нога|ноги|рука|руки|грудь|шея|поясница|колено|горло)"
    r"\s*$",
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
    if re.search(r"\bплохо\s+спал\w*\b|\bне\s+спал\w*\b|\bбессон\w*\b", n):
        add(
            label="плохой сон",
            kind="sleep_problem",
            body_site=None,
            role="primary" if first_symptom else "independent",
            quote=clause,
        )

    # Generic construction fallback: ANY noun + pain verb is a body site.
    # The specific rules above keep their canonical labels; this only runs
    # when a clause produced no mention, so it closes the whole class of
    # holes (зуб, спина, нога, горло, ухо, ребро, ...) without a body-part
    # list. Live fs-4d8f5a8b: «Начал зук болит у меня.» extracted NOTHING and
    # the freshest symptom was lost at summary.
    if not mentions or not any(m.role in ("primary", "independent") for m in mentions):
        for g in _GENERIC_BODY_PAIN.finditer(n):
            site = g.group(1).strip()
            if not site or _NON_BODY_NOUN.search(site):
                continue
            add(
                label=f"{site} болит",
                kind="symptom",
                body_site=site,
                role="primary" if first_symptom else "independent",
                quote=clause,
            )
            first_symptom = False
            break
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
    r"\s*[,;]\s*|\s+(?:а|но|однако)\s+",
    re.I,
)
_SPEAKER_SIGNAL_RE = re.compile(
    r"\b(?:я|мне|меня|мной|мною|у\s+меня|сам|сама)\b",
    re.I,
)


_GENERIC_BODY_PAIN = re.compile(
    r"\b([а-яё]{3,})\b"
    r"(?:\s+(?:сильно|очень|немного|чуть|ещ[её]|тоже|постоянно|давно|"
    r"невыносимо|нестерпимо|страшно))?"
    r"\s+(?:болит|болит[аиуы]?|ноет|ноют|ломит|ломит[аи]?|давит|стреляет|"
    r"стрелял|жж[её]т|жг[её]т|пульсирует|колет|першит)\b",
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
        suppress_health_issues_for_non_complaint_frame,
    )

    # False-world frames (dream/film, other-person, joke, past-resolved):
    # never speaker ISSUE_SITE (map docs/plans/Understand-false-worlds.md).
    if suppress_health_issues_for_non_complaint_frame(raw):
        return ()

    # Mixed subjects («у мужа плохо, а у меня голова болит»): keep speaker
    # clauses only — mirror extract_goal_facts other-person split.
    _low = raw.lower().replace("ё", "е")
    if _CLAUSE_SPLIT_RE.search(raw) and _SPEAKER_SIGNAL_RE.search(_low):
        from packages.dialogue_engine.check_path import is_other_person_health_frame

        _parts = _CLAUSE_SPLIT_RE.split(raw)
        _kept = [
            p.strip()
            for p in _parts
            if p.strip() and not is_other_person_health_frame(p.strip())
        ]
        if not _kept:
            return ()
        raw = " ".join(_kept).strip()
        raw = re.sub(r"^(?:а|но|однако)\s+", "", raw, flags=re.I).strip()
        if not raw:
            return ()

    parts = _split_symptom_parts(raw)
    all_mentions: list[IssueMention] = []
    shared_verb = any(bool(_PAIN_VERB.search(p.lower())) for p in parts)
    first = True
    for part in parts:
        bare_site = shared_verb and bool(_BARE_SITE_CLAUSE.match(part.strip().lower()))
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
