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
