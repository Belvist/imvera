"""Adaptive coverage — MVP-faithful, not a questionnaire.

The client is not a form: Vera must cover up to 5 wellbeing domains
(wellbeing / mood / sleep / medication / nutrition), but only what is still
unknown. Anything the client already volunteered counts as covered and is
never re-asked. Minimum bar (MVP numbers): 3 content exchanges and
3 covered domains before IMPORTANT_TO_SHARE → summary may close the call.

Emergency (URGENT) bypasses coverage entirely — handled before this module.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from packages.dialogue_engine.protocol import coverage_order as _coverage_order
from packages.dialogue_engine.semantic_kernel.lexicon import (
    MEDICATION_WORDS,
    MOOD_WORDS_NEG,
    MOOD_WORDS_POS,
    SLEEP_WORDS,
)

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState

MIN_CONTENT_QUESTIONS = 3
MIN_COVERED_DOMAINS = 3

DOMAINS: tuple[str, ...] = ("wellbeing", "mood", "sleep", "medication", "nutrition")

# Baseline filler priority: food first, then meds (neutral check only after
# the meal question — never nag right after «хорошо»). Mood/sleep last.
# Generated from the protocol table (single source); do not fork a copy.
FILLER_ORDER: tuple[str, ...] = _coverage_order("full")

_MOOD_MARKERS = re.compile(
    r"(груст|одинок|тревож|триво|настроени|тоскл|весел|радост|"
    + "|".join(sorted(MOOD_WORDS_NEG | MOOD_WORDS_POS))
    + r")",
    re.I,
)
_SLEEP_MARKERS = re.compile(
    r"(спал|сплю|сон|бессон|высп|недоспал|проснул|заснуть|дрем|вороча|кошмар|храп|снотворн|"
    + "|".join(sorted(SLEEP_WORDS))
    + r")",
    re.I,
)
_MEDICATION_MARKERS = re.compile(
    r"(таблет|лекар|препарат|медикамент|капа\w*\s+в\s+глаза|покапа|"
    + "|".join(sorted(MEDICATION_WORDS))
    + r")",
    re.I,
)
_NUTRITION_MARKERS = re.compile(
    r"(поел|поела|покушал|кушал\w*|пообедал|поужинал|позавтракал|аппетит|"
    r"\bел[аи]?\b|\bпил[аи]?\b|голод|попил|воды|ел\s+сегодня|пирож|суп|каш|макарон|"
    # Food words are whole-word matched: short stems («чай», «рис», «сок»,
    # «щи», «уха», «мед») collide as substrings («случайно», «борис»,
    # «высоко», «женщина», «ухаживать», «медсестра»).
    r"\b(?:завтрак\w*|обед\w*|ужин\w*|полдник\w*|суп[ауом]*|каш[ауои]\w*|хлеб\w*|"
    r"булк\w*|булоч\w*|ча[ейюемя]|кофе|молок\w*|кефир\w*|яблок\w*|"
    r"банан\w*|апельсин\w*|картошк\w*|картофел\w*|макарон\w*|рис[ауом]*|"
    r"гречк\w*|гречн\w*|мяс\w*|рыб\w*|куриц\w*|яйц\w*|сыр[ауом]*|творог\w*|"
    r"сметан\w*|масл\w*|сахар\w*|сол[ьи]\w*|вод\w*|сок\w*|компот\w*|"
    r"кисел\w*|пирог\w*|пирож\w*|печенье|печенья|печенью|конфет\w*|м[её]д[ауом]*|"
    r"варен[ье]\w*|салат\w*|овощ\w*|фрукт\w*|котлет\w*|сосис\w*|"
    r"колбас\w*|пельмен\w*|борщ\w*|уха\b|щи\b|окрошк\w*|блин\w*|"
    r"олад\w*|яичниц\w*|омлет\w*|бутерброд\w*)\b)",
    re.I,
)


def _all_user_text(state: EngineState) -> str:
    bits: list[str] = []
    for key in ("important_to_share", "wellness_concern", "wellness_duration"):
        val = state.observations.get(key) or getattr(state, key, "")
        if val:
            bits.append(str(val))
    for slot in ("wellness", "mood", "sleep", "plans"):
        val = state.slot_values.get(slot)
        if val:
            bits.append(str(val))
    for ev_list in state.topic_evidence.values():
        for ev in ev_list:
            bits.append(ev.clause)
    for ep in state.issue_episodes.values():
        bits.append(ep.primary_label or "")
        for attr in ("onset", "duration", "severity", "current", "pattern",
                     "daytime_impact", "intake", "barrier", "status_today"):
            val = ep.known_attributes.get(attr)
            if val and not str(val).startswith("_product_asked"):
                bits.append(str(val))
    return " ".join(bits)


def covered_domains(state: EngineState) -> set[str]:
    """Domains with real evidence — asked+answered OR volunteered."""
    from packages.contracts.enums import SlotStatus

    covered: set[str] = set()
    if state.slots.get("wellness") == SlotStatus.FILLED:
        covered.add("wellbeing")
    if state.slots.get("mood") == SlotStatus.FILLED:
        covered.add("mood")
    if state.slots.get("sleep") == SlotStatus.FILLED:
        covered.add("sleep")

    text = _all_user_text(state)
    if _MOOD_MARKERS.search(text):
        covered.add("mood")
    if _SLEEP_MARKERS.search(text):
        covered.add("sleep")
    if _MEDICATION_MARKERS.search(text) or state.medication_asked:
        covered.add("medication")
    if _NUTRITION_MARKERS.search(text):
        covered.add("nutrition")
    # Filler answers are recorded verbatim (fact-checks, not extractions).
    for domain in DOMAINS:
        if state.observations.get(f"coverage_{domain}"):
            covered.add(domain)
    for ep in state.issue_episodes.values():
        label = (ep.primary_label or "").lower()
        kind = (ep.kind or "").lower()
        if kind == "sleep_problem" or "сон" in label or "спал" in label:
            covered.add("sleep")
        if "таблет" in label or "лекар" in label:
            covered.add("medication")
    return covered


def content_exchanges(state: EngineState) -> int:
    """Answered content turns: filled check slots + grounded episodes."""
    from packages.contracts.enums import SlotStatus

    n = sum(
        1
        for slot in ("wellness", "mood", "sleep", "plans")
        if state.slots.get(slot) == SlotStatus.FILLED
    )
    n += sum(
        1 for ep in state.issue_episodes.values() if ep.known_attributes
    )
    if state.observations.get("important_to_share"):
        n += 1
    return n


def coverage_met(state: EngineState) -> bool:
    return (
        content_exchanges(state) >= MIN_CONTENT_QUESTIONS
        and len(covered_domains(state)) >= MIN_COVERED_DOMAINS
    )


def next_uncovered_domain(
    state: EngineState, *, skip_asked: bool = True
) -> str | None:
    covered = covered_domains(state)
    asked = state.coverage_asked_domains if skip_asked else frozenset()
    for domain in FILLER_ORDER:
        if domain not in covered and domain not in asked:
            return domain
    return None


def coverage_reply_quote(turn, domain: str) -> str | None:
    """Evidence about this domain, never just a substantive answer act.

    Reuse Understand's clause/subject owners and the domain vocabulary already
    used for coverage. This is a relevance gate, not a positive/negative judge.
    The renderer must not infer an outcome from this quote.
    """
    from packages.dialogue_engine.deterministic_mission import split_mission_clauses
    from packages.dialogue_engine.reluctance import _SHORT_CONTENT_VERBS
    from packages.dialogue_engine.semantic_kernel.controls import is_local_question_refusal
    from packages.dialogue_engine.semantic_kernel.lexicon import FOOD_WORDS
    from packages.dialogue_engine.semantic_kernel.morphology import normalize_token
    from packages.dialogue_engine.semantic_kernel.subject_resolver import _subject_for_clause
    from packages.dialogue_engine.semantic_kernel.types import SubjectKind

    raw = (turn.raw_text or "").strip()
    if (
        not raw or turn.user_question or turn.control not in ("", "none")
        or turn.not_recalled or is_local_question_refusal(raw)
    ):
        return None
    for fact in turn.goal_facts:
        if fact.field == domain and fact.subject != "other":
            quote = fact.evidence.quote.strip()
            if quote and quote in raw:
                return quote
    bare = None
    for clause in split_mission_clauses(raw):
        text = clause.text
        tokens = set(re.findall(r"[а-яё]+", text.casefold()))
        if (_subject_for_clause(text, has_issue=False) == SubjectKind.OTHER_PERSON
                or {"он", "она", "они", "оно"}.intersection(tokens)):
            continue
        core = text.casefold().strip().rstrip(".!?…")
        if core in {"да", "нет", "неа", "конечно"}:
            bare = text
            continue
        food_object = bool(FOOD_WORDS.intersection(normalize_token(word) for word in tokens))
        if domain == "medication" and not _MEDICATION_MARKERS.search(text):
            scoped = turn.model_copy(update={"raw_text": text, "goal_facts": ()})
            if food_object or nutrition_reply_record(scoped) is not None:
                continue
        if (domain == "nutrition" and _MEDICATION_MARKERS.search(text)
                and not _NUTRITION_MARKERS.search(text)):
            continue
        if domain == "medication" and classify_medication_screen(text) != "unclear":
            return text
        marker = _DOMAIN_MARKERS.get(domain)
        if marker is not None and marker.search(text):
            return text
        if domain in ("nutrition", "medication") and _SHORT_CONTENT_VERBS.search(text):
            return text
    return bare


def nutrition_reply_record(turn, *, answering: bool = False):
    """Ground intake tense/negation once; never promote a topic to an outcome.

    Only speaker-owned past-tense ingestion, or a bare contextual yes/no, can
    establish ate/not-ate. Future, infinitive, uncertain, quoted and other-person
    predicates abstain. Uses existing morphology and clause/negation owners.
    """
    from packages.dialogue_engine.context import SlotValue
    from packages.dialogue_engine.deterministic_mission import (
        _clause_uncertain,
        _is_user_question,
        split_mission_clauses,
    )
    from packages.dialogue_engine.fast_interpreter import _detect_polarity
    from packages.dialogue_engine.semantic_kernel.controls import is_local_question_refusal
    from packages.dialogue_engine.semantic_kernel.morphology import _load_morph
    from packages.dialogue_engine.semantic_kernel.subject_resolver import _subject_for_clause
    from packages.dialogue_engine.semantic_kernel.types import SubjectKind
    from packages.safety.patterns import is_negated_at, is_past_without_present

    raw = (turn.raw_text or "").strip()
    from packages.dialogue_engine.check_path import is_narrative_fiction_frame

    if (turn.not_recalled or turn.user_question or _is_user_question(raw)
            or turn.control not in ("", "none") or is_local_question_refusal(raw)
            or any(mark in raw for mark in ('"', '«', '»'))
            or is_narrative_fiction_frame(raw)):
        return None
    morph = _load_morph()
    if morph is None:
        return None
    clauses = split_mission_clauses(raw)
    record = None
    for index, clause in enumerate(clauses):
        tokens = re.findall(r"[а-яё]+", clause.text.casefold())
        if (_subject_for_clause(clause.text, has_issue=False) == SubjectKind.OTHER_PERSON
                or {"он", "она", "они", "оно", "если", "бы"}.intersection(tokens)
                or _clause_uncertain(clauses, index) or is_past_without_present(clause.text)):
            continue
        for match in re.finditer(r"[а-яё]+", clause.text, re.I):
            parses = morph.parse(match.group())
            if not parses:
                continue
            parsed = parses[0]
            # A small closed predicate vocabulary, inflected by morphology,
            # instead of copying hundreds of surface forms into the renderer.
            if (getattr(parsed, "score", 0.0) < .5
                    or parsed.tag.POS != "VERB" or parsed.tag.tense != "past"
                    or parsed.normal_form not in {
                        "есть", "поесть", "кушать", "покушать", "завтракать", "позавтракать",
                        "обедать", "пообедать", "ужинать", "поужинать",
                    }):
                continue
            if any("Name" in item.tag and "nomn" in item.tag for word in
                   re.findall(r"[а-яё]+", clause.text[:match.start()], re.I)
                   for item in morph.parse(word)[:1]):
                continue
            # A reported fictional/past-resolved world is not today's intake.
            from packages.dialogue_engine.discourse import _speech_owned_elsewhere

            if any(_speech_owned_elsewhere(clause.text)):
                continue
            negative = is_negated_at(clause.text, match.start())
            prefix = clause.text[:match.start()].casefold().split()
            if negative and not (prefix and (
                prefix[-1] == "не" or (len(prefix) >= 2 and prefix[-2] == "не"
                and prefix[-1] in {"ещё", "еще", "пока", "совсем", "вовсе"})
            )):
                continue
            if not negative and _detect_polarity(clause.text) == "negative":
                continue
            record = SlotValue(
                value="not_eaten" if negative else "eaten",
                polarity="negative" if negative else "positive", confirmed=True,
                source_text=clause.text, source_turn_id=turn.utterance_id,
            )
    if record is not None:
        return record
    core = raw.casefold().strip().rstrip(".!?…")
    if answering and core in {"да", "нет", "неа"}:
        negative = core != "да"
        return SlotValue(
            value="not_eaten" if negative else "eaten",
            polarity="negative" if negative else "positive", confirmed=True,
            source_text=raw, source_turn_id=turn.utterance_id,
        )
    return None


_DOMAIN_MARKERS: dict[str, re.Pattern[str]] = {
    "mood": _MOOD_MARKERS,
    "sleep": _SLEEP_MARKERS,
    "medication": _MEDICATION_MARKERS,
    "nutrition": _NUTRITION_MARKERS,
}

# Thread bonus: mentioning a domain is worth more than position in line.
# Mission weights stay equal (all required) — order follows the person,
# ties fall back to FILLER_ORDER. Deterministic, microseconds, traced.
THREAD_BONUS = 2.0


def score_domain(
    domain: str, *, last_user_text: str, order_index: int
) -> tuple[float, dict[str, float]]:
    """Utility score + feature breakdown (explainable in trace/tests)."""
    features = {
        "information": 1.0,
        "thread": (
            THREAD_BONUS
            if _DOMAIN_MARKERS[domain].search(last_user_text or "")
            else 0.0
        ),
        "position": -0.1 * order_index,
    }
    return sum(features.values()), features


def scored_next_domain(
    state: EngineState, last_user_text: str, *, skip_asked: bool = True
) -> str | None:
    """Next coverage domain by utility, not by fixed order.

    Same candidates as next_uncovered_domain; the person’s own topic wins
    («спал плохо» → sleep next, not nutrition). Ties → FILLER_ORDER.
    """
    covered = covered_domains(state)
    asked = state.coverage_asked_domains if skip_asked else frozenset()
    best: str | None = None
    best_key: tuple[float, int] | None = None
    for order_index, domain in enumerate(FILLER_ORDER):
        if domain in covered or domain in asked:
            continue
        score, _ = score_domain(
            domain, last_user_text=last_user_text, order_index=order_index
        )
        key = (score, -order_index)
        if best_key is None or key > best_key:
            best_key = key
            best = domain
    return best


def domain_question(domain: str, *, variant: int = 0) -> tuple[str, str, str]:
    """(text, intent, slot) for one baseline filler — asked at most once.

    Variants rotate deterministically per call (no robot repetition).
    Medication is a two-step conditional: screening first («принимаете?»),
    «сегодня приняли?» only for those who do — never for the rest.
    """
    if domain == "mood":
        texts = (
            "А настроение сегодня как — ничего не тревожит?",
            "Как настроение? Ничего не беспокоит?",
        )
        return (texts[variant % len(texts)], "background_mood", "mood")
    if domain == "sleep":
        texts = (
            "А спалось сегодня нормально?",
            "А ночью как спали — выспались?",
        )
        return (texts[variant % len(texts)], "background_sleep", "sleep")
    if domain == "medication":
        # Neutral screening (product spec): no prescriptions, no dosage talk,
        # no «не забудьте». The question itself is the soft reminder.
        texts = (
            "Есть ли у вас лекарства, которые вы обычно принимаете?",
            "Скажите, а у вас есть лекарства, которые вы принимаете обычно?",
        )
        return (texts[variant % len(texts)], "background_medication", "background_medication")
    if domain == "nutrition":
        texts = (
            "А покушать сегодня уже успели?",
            "Как сегодня с едой — нормально поели?",
        )
        return (texts[variant % len(texts)], "background_nutrition", "background_nutrition")
    return ("Как вы себя чувствуете?", "check_wellness", "wellness")


MEDICATION_TODAY_TEXTS = (
    "Сегодня уже принимали?",
    "Сегодня уже принимали то, что обычно принимаете?",
)

_NO_DAILY_MEDS = re.compile(
    r"\b(не\s+принимаю|не\s+пью|не\s+назначили|не\s+назначено|"
    r"не\s+каждый\s+день|не\s+всегда|"
    r"без\s+лекарств|не\s+надо|ничего\s+не\s+пью|"
    r"^(нет|неа)\.?$)",
    re.I,
)
# As-needed («только иногда, если нужно») still earns the today question
# (spec scenario 8) — without any instruction to take.
_OCCASIONAL_MEDS = re.compile(
    r"(иногда|время\s+от\s+времени|когда\s+нужно|если\s+нужно|"
    r"по\s+необходимости|не\s+постоянно)",
    re.I,
)
_MEDICATION_REFUSE = re.compile(
    r"(не\s+хочу\s+(про\s+это|об\s+этом\s+)?говорить|"
    r"не\s+буду\s+(про\s+это\s+)?говорить|"
    r"давай\s+не\s+будем\s+про\s+это)",
    re.I,
)
_TAKES_DAILY_MEDS = re.compile(
    r"\b(принимаю|принимал\w*|пью|назначено|назначили|конечно|обязательно|"
    r"каждый\s+день|раскладывает|да[её]т\s+(дочь|жена|сын)|"
    r"несколько\s+разных)\b|^(да|ага|угу|конечно)\.?$|^(да,?\s*)?есть\b",
    re.I,
)
_ALREADY_TOOK_TODAY = re.compile(
    r"\b(принял[аи]?|выпил[аи]?|уже\s+да|только\s+что)\b",
    re.I,
)
# Negated take («не выпил», «не принимал») = today-status KNOWN negative:
# record and done, never a followup (live 780904ae «Есть, но не выпил»).
_NEGATED_TOOK_TODAY = re.compile(
    r"\bне\s+(принял\w*|выпил\w*|пил\w*|принимал\w*|приняла?)\b",
    re.I,
)


def classify_medication_screen(raw: str) -> str:
    """no_meds | takes_meds | already_took | refused | unclear."""
    text = (raw or "").strip().lower()
    if _MEDICATION_REFUSE.search(text):
        return "refused"
    if _NO_DAILY_MEDS.search(text):
        return "no_meds"
    if _NEGATED_TOOK_TODAY.search(text) or _ALREADY_TOOK_TODAY.search(text):
        return "already_took"
    if _OCCASIONAL_MEDS.search(text) or _TAKES_DAILY_MEDS.search(text):
        return "takes_meds"
    if re.search(r"\b(есть|имеются|имеется)\b", text):
        # Existential «есть» in the screener context = takes (spec: «кое-что
        # есть»). \b-safe: «поесть»/«вместе» never match.
        return "takes_meds"
    return "unclear"
