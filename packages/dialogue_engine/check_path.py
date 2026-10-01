"""Daily-check branching — table-driven wellness paths and probe transitions."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState

_PAIN = re.compile(
    r"\b(болит|боль|болел\w*|болела|приболел\w*|заболел\w*|разболел\w*|поболел\w*|побалива\w*|поныва\w*|прихватило|схватило|вступило|голова|головн\w*|живот|спина|сустав|"
    r"давлен\w*|температур\w*|кашел\w*|тошн\w*|слабост\w*|одышк\w*)\b",
    re.I,
)
_SYMPTOM_DETAIL = re.compile(
    r"\b(кружит\w*|тошн\w*|слабост\w*|одышк\w*|температур\w*|"
    r"вс[её]\s+болит|ничего\s+не\s+радует)\b",
    re.I,
)
_URGENT = re.compile(
    r"\b(скор(ую|ая|ой)\b|срочн\w*|помогите|спасите|не\s+могу\s+дышать|"
    r"задыха\w*|удуш\w*|"
    r"кровь|потеря\w*\s+сознан|теря\w*\s+сознан|"
    r"упал\w*|падаю|падают|не\s+могу\s+встать|"
    r"умира\w*|умр\w*|"
    r"очень\s+сильн\w*|ужасн\w*\s+боль|"
    r"вызов\w*\s+скор\w*|вызови(те)?\s+скор\w*|инфаркт|инсульт|"
    r"сердечн\w*\s+приступ|сердц\w*\s+давит|давит\w*\s+сердц\w*|"
    r"бол(?!ее(?:\b|-))\w*\s+в\s+груд\w*)\b",
    re.I,
)
_DURATION_HINT = re.compile(
    r"\b(давно|раньше|дня|дней|недел|месяц|час|утр|вчера|сегодня|"
    r"сейчас|уже|назад|только\s+что|"
    r"понедельн\w*|вторник\w*|сред\w*|четверг\w*|пятниц\w*|суббот\w*|воскресен\w*|"
    r"второй\s+день|третий\s+день|пару\s+дней|несколько|с\s+утра|"
    r"уже\s+\w+\s+дн|\b\d{1,2}:\d{2}\b|"
    r"(в|на|к|с)\s+(час|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять|"
    r"одиннадцать|двенадцать)(\s+(часов|часа|утра|дня|вечера|ночи))?)\b",
    re.I,
)
_SYMPTOM_HEAD = re.compile(r"\b(голов\w*|головн\w*\s+бол\w*)\b", re.I)
_SYMPTOM_STOMACH = re.compile(r"\b(живот|тошн\w*|рвот\w*)\b", re.I)
_SYMPTOM_BACK = re.compile(r"\b(спин\w*|поясниц\w*)\b", re.I)
_SYMPTOM_PRESSURE = re.compile(r"\b(давлен\w*|гипертон\w*)\b", re.I)
_OK_BUT_PAIN = re.compile(
    r"\b(нормально|хорошо|терпимо|сойд\w*|пойд\w*)\b",
    re.I,
)
_CONTRAST = re.compile(r"\b(но|хотя)\b", re.I)


class ProbeAction(StrEnum):
    SPEAK_PROBE = "speak_probe"
    SPEAK_SLOT = "speak_slot"
    SPEAK_PLANS = "speak_plans"
    URGENT_CLOSE = "urgent_close"
    CONTINUE_LADDER = "continue_ladder"


@dataclass(frozen=True)
class WellnessBranch:
    """First matching rule wins — explicit priority, no nested if/else."""

    path: str
    probe_phase: str | None = None
    skip_mood_sleep: bool = False
    store_concern_from_wellness: bool = False
    urgent: bool = False


@dataclass(frozen=True)
class ProbeStep:
    action: ProbeAction
    probe_phase: str | None = None
    next_slot: str | None = None
    ack_polarity: str | None = None


def has_pain_mention(text: str) -> bool:
    """Pain mention outside negation (live hard-battery: denied pain is
    absence of complaint, never a probe trigger). Clause-scoped via the
    shared safety guards: "голова болит" hits, "ничего не болит" misses,
    "не очень, голова болит" hits (second clause is clean)."""
    from packages.safety.patterns import is_negated_at, split_clauses

    for clause in split_clauses(text or ""):
        for match in _PAIN.finditer(clause):
            if not is_negated_at(clause, match.start()):
                return True
    return False


def has_symptom_detail(text: str) -> bool:
    return has_pain_mention(text) or bool(_SYMPTOM_DETAIL.search(text or ""))


def wellness_already_describes_concern(text: str) -> bool:
    """True only when wellness text names a concrete symptom/concern.

    Length alone is not evidence — «состояние плохое» is still vague.
    """
    normalized = (text or "").strip()
    if not normalized:
        return False
    return has_symptom_detail(normalized)


# Phonetic tolerance for the safety lexicon (STT slurs vowels/nasals:
# «умираю»→«унираю»/«умилаю»). Rule: FIRST letter literal (onsets are
# reliable; fuzzifying it matches «вода» for «пада»), the tail uses
# confusion classes. Short stems keep \b anchors against «задание».
_FUZZ = {
    "м": "[мн]", "н": "[мн]",
    "о": "[оа]", "а": "[оа]",
    "и": "[иеы]", "е": "[иеы]", "ы": "[иеы]",
    "г": "[гк]", "к": "[гк]", "д": "[дт]", "т": "[дт]",
    "б": "[бп]", "п": "[бп]", "в": "[вф]", "ф": "[вф]",
    "з": "[зс]", "с": "[зс]", "ж": "[жш]", "ш": "[жш]",
    "р": "[рл]", "л": "[рл]",
}


def _fz(word: str) -> str:
    """First letter literal + confusion classes for the tail."""
    return word[0] + "".join(_FUZZ.get(c, c) for c in word[1:])


# Immediate red action — never clarify first (falling, choking, blood,
# explicit help call, chest pain/pressure, can't get up, stroke/heart signs).
# Stems are truncation-tolerant (STT cuts «задыхаюсь»→«зады.»): short
# distinctive prefixes included deliberately; the set stays semantic
# (fall/choke/die/blood/help), never generic pain.
_URGENT_ACTION = re.compile(
    r"\b(скор(ую|ая|ой)\b|срочн\w*|помогите|спасите|не\s+могу\s+дышать|"
    r"не\s+хватает\s+воздуха|нехватка\s+воздуха|"
    + _fz("задыха")
    + r"\w*|зад[аы]\b|удуш\w*|"
    r"кровь|кро[вф]ь|"
    r"потеря\w*\s+сознан\w*|теря\w*\s+сознан\w*|без\s+сознания|"
    r"упал\w*|упан\w*|упа[рл]\w*|пада\w*|пад[ао]\b|\bпад\b|не\s+могу\s+встать|"
    r"вызов\w*\s+скор\w*|вызови(те)?\s+скор\w*|вызывайте\s+скор\w*|"
    r"инфаркт|инсульт|"
    r"сердечн\w*\s+приступ|"
    r"сердц\w*\s+(давит|болит|колет|сжимает|щемит)|"
    r"давит\w*\s+сердц\w*|"
    r"давлен\w*\s+2\d\d|"
    r"бол(?!ее(?:\b|-))\w*\s+в\s+груд\w*)\b",
    re.I,
)
# Red state without a concrete complaint («умираю», «мне конец», «ужасно») —
# clarify WHAT happened first, then escalate (asked, never assumed).
_URGENT_STATE = re.compile(
    r"\b("
    + _fz("умира")
    + r"\w*|умир\w*|у[мн][иеы]р\b|\bуми\b|умр\w*|помираю|мне\s+конец|очень\s+плохо|"
    r"очень\s+сильн\w*|ужасн\w*(\s+боль)?|кошмар\w*|мне\s+плохо\s+совсем)\b",
    re.I,
)


def is_urgent_concern(text: str) -> bool:
    """Any red signal (action or state) — compatibility entry point."""
    return is_urgent_action(text) or is_urgent_state(text)


def is_urgent_action(text: str) -> bool:
    from packages.safety.patterns import match_guarded

    return match_guarded(_URGENT_ACTION, text or "") is not None


def is_urgent_state(text: str) -> bool:
    from packages.safety.patterns import match_guarded

    if is_urgent_action(text):
        return False
    # Joke/hyperbole («умру от смеха», «шучу») is not a medical red state.
    if is_joke_hyperbole_frame(text or ""):
        return False
    return match_guarded(_URGENT_STATE, text or "") is not None


def looks_like_duration_answer(text: str) -> bool:
    from packages.dialogue_engine.issue_memory import extract_grounded_onset_value

    return extract_grounded_onset_value(text or "") is not None


def _pain_ok_but(text: str) -> bool:
    return bool(_CONTRAST.search(text) and _OK_BUT_PAIN.search(text) and has_pain_mention(text))


def classify_wellness_path(
    *,
    wellness_text: str,
    polarity: str | None,
) -> WellnessBranch:
    from packages.dialogue_engine.state import CheckPath
    from packages.dialogue_engine.topic_tracker import TopicFamily, detect_families

    text = (wellness_text or "").lower()
    rules: tuple[tuple[Callable[[], bool], WellnessBranch], ...] = (
        (
            lambda: TopicFamily.SLEEP in detect_families(text),
            WellnessBranch(path=CheckPath.STANDARD),
        ),
        (
            # Past-resolved pain is history, not a current complaint:
            # never store it as concern or open pain probes (false-worlds).
            # Present pivots ("а сейчас болит") fall through below.
            lambda: is_past_noncurrent_frame(wellness_text or ""),
            WellnessBranch(path=CheckPath.STANDARD),
        ),
        (
            lambda: is_urgent_concern(text),
            WellnessBranch(path=CheckPath.URGENT, urgent=True, store_concern_from_wellness=True),
        ),
        (
            lambda: _pain_ok_but(text),
            WellnessBranch(
                path=CheckPath.PAIN_SHORT,
                probe_phase="pain_night",
                skip_mood_sleep=True,
                store_concern_from_wellness=True,
            ),
        ),
        (
            lambda: has_pain_mention(text) and polarity in (None, "positive", "uncertain"),
            WellnessBranch(
                path=CheckPath.PAIN_SHORT,
                probe_phase="pain_night",
                skip_mood_sleep=True,
                store_concern_from_wellness=True,
            ),
        ),
        (
            lambda: polarity == "negative" and wellness_already_describes_concern(text),
            WellnessBranch(
                path=CheckPath.NEGATIVE_PROBE,
                probe_phase="duration",
                store_concern_from_wellness=True,
            ),
        ),
        (
            lambda: polarity == "negative",
            WellnessBranch(path=CheckPath.NEGATIVE_PROBE, probe_phase="concern"),
        ),
        (
            lambda: has_pain_mention(text),
            WellnessBranch(
                path=CheckPath.PAIN_SHORT,
                probe_phase="pain_night",
                skip_mood_sleep=True,
                store_concern_from_wellness=True,
            ),
        ),
    )
    for matches, branch in rules:
        if matches():
            return branch
    return WellnessBranch(path=CheckPath.STANDARD)


def apply_wellness_branch(state: EngineState, branch: WellnessBranch) -> None:
    state.check_path = branch.path
    if branch.store_concern_from_wellness:
        rec = state.slot_records.get("wellness")
        state.wellness_concern = (
            (rec.source_text if rec else "")
            or state.slot_values.get("wellness", "")
        )
    if branch.skip_mood_sleep:
        state.skipped_slots.update({"mood", "sleep"})
    state.probe_phase = branch.probe_phase


_PROBE_FLOW: dict[str, Callable[[EngineState, str], ProbeStep]] = {}


def _register_probe(phase: str, handler: Callable[[EngineState, str], ProbeStep]) -> None:
    _PROBE_FLOW[phase] = handler


_EXPLICIT_DECLINE_RE = re.compile(
    r"(ничего\s+не\s+(болит|беспокоит|тревожит)|"
    r"не\s+(болит|беспокоит)\b|"
    r"\bнет\b.{0,25}(хорошо|нормально|отлично)|"
    r"вс[её]\s+хорошо|вс[её]\s+нормально|вс[её]\s+отлично)",
    re.I,
)


_POLITENESS_REFUSAL_RE = re.compile(
    r"(?:"
    r"\bне\s+(?:беспокой|беспокоить|надо\s+беспокоить|спрашивай|спрашивать|"
    r"надо\s+спрашивать|расспрашивай)\b|"
    r"\bне\s+хочу\s+(?:об\s+этом\s+)?(?:говорить|разговаривать|рассказывать)\b|"
    r"\bне\s+надо\s+(?:мне\s+)?(?:вопросов|спрашивать)\b|"
    r"\bоставьте\s+меня\b|"
    r"\bбольше\s+не\s+(?:спрашивай|спрашивайте|беспокой|беспокоить)\b"
    r")",
    re.I,
)


def is_politeness_refusal(text: str) -> bool:
    """The elder asks to stop being probed.

    Distinct from denial of a complaint: «не беспокой меня» does not mean
    «у меня ничего не болит» — it means «stop asking». Routing both through
    one predicate is why the refusal used to be answered with the next
    question (live fs-4d8f5a8b).

    Honoring it stops the routine question ladders only. A symptom reported
    after a refusal still opens ISSUE_SITE — safety and grounding outrank
    politeness.
    """
    t = (text or "").strip()
    if not t:
        return False
    if complaint_without_negation(t):
        return False
    return bool(_POLITENESS_REFUSAL_RE.search(t))


def is_explicit_concern_decline(text: str) -> bool:
    """Explicit denial-of-complaint (live fs-6e3abff0) — accept at once.

    Denial shapes only ("ничего не болит", "нет, всё хорошо"). Bare
    positives ("Нормально.", "Хорошо.") are NOT declines here — they ride
    the normal answer flow (WELLNESS_OK territory). Vague ("Поел.",
    "Не скажу.") still earns ONE options ask; hostile still escalates.
    Guarded by complaint_without_negation: any unnegated complaint wins.
    """
    t = (text or "").strip()
    if not t or complaint_without_negation(t):
        return False
    return bool(_EXPLICIT_DECLINE_RE.search(t))


def apply_concern_answer(state: EngineState, text: str) -> str:
    """Single owner for concern-probe answers (rich and semantic paths).

    A complaint grounds wellness_concern; urgent text arms the urgent path;
    anything else declines the concern. Returns "grounded" | "declined" |
    "urgent". Callers map the outcome to their own step/plan type.
    """
    from packages.dialogue_engine.state import CheckPath

    # A non-complaint answer («поел», «нормально») DECLINES the concern —
    # never record food as WHAT hurts, never start a duration probe on it
    # (live fs-a1dca80c: «поел» → «как давно продолжается?»).
    if not _looks_like_complaint(text):
        state.probe_phase = None
        state.observations["concern_declined"] = "1"
        return "declined"
    # Past-resolved frames («раньше болела, сейчас хорошо») are history,
    # not a current concern — same decline path, no probes (false-worlds).
    # Present pivots («а сейчас болит») fall through to grounding below.
    if is_past_noncurrent_frame(text):
        state.probe_phase = None
        state.observations["concern_declined"] = "1"
        return "declined"
    state.wellness_concern = text
    if is_urgent_concern(text):
        state.check_path = CheckPath.URGENT
        state.probe_phase = None
        return "urgent"
    state.probe_phase = "duration"
    return "grounded"


def _probe_concern(state: EngineState, text: str) -> ProbeStep:
    outcome = apply_concern_answer(state, text)
    if outcome == "declined":
        return ProbeStep(action=ProbeAction.CONTINUE_LADDER)
    if outcome == "urgent":
        return ProbeStep(action=ProbeAction.URGENT_CLOSE)
    return ProbeStep(action=ProbeAction.SPEAK_PROBE, probe_phase="duration")



# Dream / film / news / story frame: body talk inside narrative is NOT a
# speaker health complaint (live fs-80cf029f «во сне… руку тянул» → false
# ISSUE_SITE/onset). Same class as movie_dying hard-battery.
_NARRATIVE_FICTION_FRAME = re.compile(
    r"(?:"
    r"\bво\s+сне\b|"
    r"\bснил(?:ось|ся|ась|ись)?\b|"
    r"\bприснил(?:ось|ся|ась|ись)?\b|"
    r"\bсон\s+такой\b|"
    r"\bфильм\w*|"
    r"\bкино\b|"
    r"\bсериал\w*|"
    r"\bпередач\w*|"
    r"\bновост\w*|"
    r"\bсказк\w*|"
    r"\bв\s+игре\b|"
    r"\bв\s+книг\w*"
    r")",
    re.I,
)
# Explicit present-tense speaker health pivot keeps real complaints even
# when a film/dream was mentioned («после фильма голова разболелась»).
# A bare site+verb buried inside the narrative clause («снилось, что голова
# болит») is not a present pivot — only speaker-anchored pivots or
# post-narrative ones («после фильма ... разболелась») escape the frame.
_NARRATIVE_FICTION_BEFORE = re.compile(
    r"\b(?:снилось|снится|приснилось|фильм\w*|сериал\w*|передач\w*|"
    r"кино|во\s+сне|сон\s+такой)\b",
    re.I,
)
_NARRATIVE_POST_MARKER = re.compile(
    r"\bпосле\s+(?:фильм\w*|сериал\w*|кино|сна|передач\w*|этого|него)\b",
    re.I,
)
_NARRATIVE_SPEAKER_PIVOT = re.compile(
    r"(?:"
    r"\bа\s+сейчас\b|"
    r"\bи\s+сейчас\b|"
    r"\bсейчас\s+(?:бол|но[ею]т|тошн|дав[аи]т|кружи)|"
    r"\bу\s+меня\s+(?:бол|но[ею]т|тошн|дав[аи]т|кружи)|"
    r"\bмне\s+(?:бол|тошн)"
    r")",
    re.I,
)
_NARRATIVE_SITE_VERB = re.compile(
    r"\b(голов[ауеы]|живот|сердц\w*|спин[ауеы]|руках?|ногах?)\s+"
    r"(?:бол|но[ею]т|лом|дав[аи]т|тян[еу]т|разболел)",
    re.I,
)


def _narrative_pivot_escapes(raw: str) -> bool:
    """Does a present-tense complaint escape the fiction frame?"""
    if _NARRATIVE_SPEAKER_PIVOT.search(raw):
        return True
    for match in _NARRATIVE_SITE_VERB.finditer(raw):
        before = raw[: match.start()]
        if _NARRATIVE_FICTION_BEFORE.search(before):
            if _NARRATIVE_POST_MARKER.search(before):
                return True
            continue
        return True
    return False


def is_narrative_fiction_frame(text: str) -> bool:
    """True when the utterance carries a dream/film/news/story frame."""
    return bool(_NARRATIVE_FICTION_FRAME.search(text or ""))


def suppress_health_issues_for_narrative_frame(text: str) -> bool:
    """Fiction/dream narrative must not open ISSUE_SITE / pain episodes.

    Suppress unless the same turn also pivots to a present speaker complaint.
    """
    raw = text or ""
    if not is_narrative_fiction_frame(raw):
        return False
    if _narrative_pivot_escapes(raw):
        return False
    return True


# --- False-world / non-complaint frames (Understand; map docs/plans/Understand-false-worlds.md) ---
# Third-party, joke/hyperbole, past-vs-current share the dream/film suppress path:
# never write speaker ISSUE_SITE / wellness_concern / onset from these frames.

_JOKE_HYPERBOLE_FRAME = re.compile(
    r"(?:"
    r"\bшучу\b|"
    r"\bшутим\b|"
    r"\bшутк\w*|"
    r"\bприкол\w*|"
    r"\bприкалыва\w*|"
    r"\bот\s+смеха\b|"
    r"\bумираю\s+от\s+смеха\b|"
    r"\bумр\w*\s+от\s+смеха\b|"
    r"\bхоть\s+вешайся\b|"
    r"\bконечно\s+шуч\w*|"
    r"\bшуч\w*\s+конечно\b"
    r")",
    re.I,
)

_PAST_TIME_MARKER = re.compile(
    r"(?:"
    r"\bраньше\b|"
    r"\bпозавчера\b|"
    r"\bвчера\b|"
    r"\bв\s+прошл(?:ом|ую|ые)\b|"
    r"\bбывало\b"
    r")",
    re.I,
)
_PAST_PAIN_VERB = re.compile(
    r"\b(?:"
    r"болел[аио]?|болели|"
    r"разболел(?:ся|ась|ось|ись)?|"
    r"поболел(?:а|о|и)?|"
    r"ныл[аио]?|ныли|"
    r"ломило|давило|тошнило"
    r")\b",
    re.I,
)
_PRESENT_PAIN_VERB = re.compile(
    r"\b(?:"
    r"болит|болят|ноет|ноют|ломит|давит|тошнит|"
    r"кружится|разболелась(?!\s+раньше)|"
    r"беспокоит|тревожит"
    r")\b",
    re.I,
)
_PRESENT_RESOLVED_OR_OK = re.compile(
    r"(?:"
    r"\bсейчас\s+(?:вс[её]\s+)?(?:хорош\w*|норм\w*|отличн\w*|не\s+бол\w*)|"
    r"\bсейчас\s+уже\s+(?:прош[её]?л\w*|не\s+бол\w*|норм\w*)|"
    r"\bа\s+сейчас\s+(?:вс[её]\s+)?(?:хорош\w*|норм\w*|отличн\w*|не\s+бол\w*)|"
    r"\bсегодня\s+(?:уже\s+)?(?:норм\w*|хорош\w*|не\s+бол\w*|прош[её]?л\w*)|"
    r"\bа\s+сегодня\s+(?:уже\s+)?(?:прош[её]?л\w*|не\s+бол\w*|норм\w*|хорош\w*)|"
    r"\bуже\s+прош[её]?л\w*|"
    r"\bуже\s+не\s+бол\w*"
    r")",
    re.I,
)
_PRESENT_ACTIVE_COMPLAINT_PIVOT = re.compile(
    r"(?:"
    r"\bа\s+сейчас\s+(?:у\s+меня\s+)?(?:бол|но[ею]т|тошн|дав[аи]т|кружи)|"
    r"\bсейчас\s+у\s+меня\s+(?:бол|плохо|тошн)|"
    r"\bи\s+сейчас\s+(?:бол|но[ею]т|тошн|вс[её]\s+ещ[её])|"
    r"\bсейчас\s+(?:бол|но[ею]т|тошн|дав[аи]т|кружи)|"
    r"\bдо\s+сих\s+пор\s+бол|"
    r"\bвс[её]\s+ещ[её]\s+бол"
    r")",
    re.I,
)

# Off-protocol chatter cues (food, visits, weather) — no symptom required.
_OFF_PROTOCOL_CHATTER = re.compile(
    r"(?:"
    r"\bсуп\w*|\bборщ\w*|\bкаш[аеиу]\b|\bед[ауие]\b|"
    r"\bварил\w*|\bготов(?:ил|лю|ит)\w*|"
    r"\bпогод\w*|\bдожд\w*|\bснег\b|"
    r"\bмагазин\w*|\bгулял\w*|\bпрогул\w*|"
    r"\bтелевизор\w*|\bпередач\w*|"
    r"\bтелик\w*|\bсериал\w*|\bновост\w*|\bмузык\w*|"
    r"\bрадио\b|\bпесн\w*|\bкино\b|\bфильм\w*|\bфутбол\w*|\bхоккей\w*|"
    r"\bконцерт\w*|\bреклам\w*|\bшоу\b|\bпрограмм\w*|\bмультик\w*|"
    r"\bприезжа\w*|\bприехал\w*|\bгостил\w*"
    r")",
    re.I,
)
_SYMPTOMISH = re.compile(
    r"(?:"
    r"\bбол(?!ее(?:\b|-))\w*|\bтошн\w*|\bкружи\w*|\bдавлен\w*|"
    r"\bтемператур\w*|\bслабост\w*|\bзадыха\w*|\bум[ие]ра\w*|"
    r"\bноет\b|\bломит\b|\bбеспокоит\b|"
    r"\bтяжест\w*|\bжжен\w*|\bрез[ьи]\b|\bломот\w*|\bколик\w*|"
    r"\bспазм\w*|\bсудорог\w*|\bонемен\w*|\bпокалыва\w*|\bзуд\w*|"
    r"\bдрож[ьи]\b|\bозноб\w*|\bпотлив\w*|\bустал\w*|\bодыш\w*|"
    r"\bудуш\w*|\bсердцебиен\w*|\bот[её]к\w*|\bсиняк\w*|\bсып[ьи]\b|"
    r"\bголовокружен\w*|\bрвот\w*|\bкашл\w*|\bнасморк\w*|\bчихан\w*|"
    r"\bикот\w*|\bотрыж\w*|\bизжог\w*|\bзапор\w*|\bпонос\w*|"
    r"\bгной\w*|\bсухост\w*|\bпершен\w*|\bгореч\w*|\bжажд\w*|"
    r"\bкров[ьи]\b"
    r")",
    re.I,
)


def is_joke_hyperbole_frame(text: str) -> bool:
    """Joke / hyperbole markers — not a medical complaint or red state."""
    return bool(_JOKE_HYPERBOLE_FRAME.search(text or ""))


_SPEAKER_HEALTH_SIGNAL = re.compile(
    r"\b(?:я|мне|меня|мной|мною|у\s+меня|сам|сама)\b",
    re.I,
)


def is_other_person_health_frame(text: str) -> bool:
    """Someone else's illness with no speaker health pivot.

    Two structural requirements, not a phrase bank:
    1. illness language in the same turn (a bare relative noun is a
       companion, not a patient: «пойду гулять с дочкой»);
    2. a third-party subject (inflection-proof: «дочь» is not a substring of
       «дочкой»/«дочери», so token matching misses real cases) and no
       speaker-health signal.

    A speaker pivot («у мужа плохо, а у меня голова болит») always wins.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    if not _SYMPTOMISH.search(raw):
        return False
    if _PRESENT_ACTIVE_COMPLAINT_PIVOT.search(raw):
        return False
    try:
        from packages.dialogue_engine.semantic_kernel.lexicon import has_other_person
    except Exception:  # noqa: BLE001
        return False
    if not has_other_person(raw):
        return False
    return not bool(_SPEAKER_HEALTH_SIGNAL.search(raw))


def is_past_noncurrent_frame(text: str) -> bool:
    """Historical pain that must not open a *current* ISSUE_SITE.

    Suppression requires an explicit non-current signal (resolved / positive
    now). A bare past marker is NOT enough: «Со вчера головная боль.»,
    «Вчера ухо заложило.» and «Живот болел вчера.» are symptoms the elder
    still reports — grounding must keep them and the onset probe is exactly
    the next useful question.
    """
    raw = text or ""
    if not raw.strip():
        return False
    if _PRESENT_ACTIVE_COMPLAINT_PIVOT.search(raw):
        return False
    has_past = bool(_PAST_TIME_MARKER.search(raw) or _PAST_PAIN_VERB.search(raw))
    if not has_past:
        return False
    if _PRESENT_RESOLVED_OR_OK.search(raw):
        return True
    # No explicit non-current signal: keep the symptom. Grounding outranks
    # the past frame — «Вчера ухо заложило.» / «Живот болел вчера.» are what
    # the elder just reported, and the onset probe is the useful next move.
    return False


def is_side_topic_chatter(text: str) -> bool:
    """Off-protocol chatter without symptom language → SIDE_TOPIC mark."""
    raw = (text or "").strip()
    if not raw:
        return False
    if not _OFF_PROTOCOL_CHATTER.search(raw):
        return False
    if _SYMPTOMISH.search(raw):
        return False
    if is_urgent_action(raw):
        return False
    return True


def suppress_health_issues_for_non_complaint_frame(text: str) -> bool:
    """Umbrella: false-world frames must not open speaker health ISSUE_SITE.

    Covers dream/film narrative, other-person-only illness, joke/hyperbole,
    and past-resolved / historical-only pain. Real present speaker pivots
    still fall through (handled inside each detector).
    """
    raw = text or ""
    if suppress_health_issues_for_narrative_frame(raw):
        return True
    if is_other_person_health_frame(raw):
        return True
    if is_joke_hyperbole_frame(raw):
        return True
    if is_past_noncurrent_frame(raw):
        return True
    return False


def _looks_like_complaint(text: str) -> bool:
    """Negation-aware complaint check (live fs-6e3abff0).

    "Ничего не беспокоит" is a decline, not a complaint. Urgent phrases
    still count (fail toward safety). All routing callers share this.
    """
    if is_urgent_concern(text):
        return True
    return complaint_without_negation(text)


_COMPLAINT_RE = re.compile(
    r"(плох|бол(?!ее(?:\b|-)|ьше)|тошн|кружи|дурно|мутит|тяжел|температур|давлен|"
    r"отвратительн|паршив|хреново|фигово|дерьмово|гнусно|мерзко|"
    r"погано|кошмарно|"
    r"слабость|болит|ноет|ломит|давит|тошнит|знобит|озноб|"
    r"беспокоит|тревожит|мешает|не\s+могу|плохо\s+себя)"
)


def complaint_without_negation(text: str) -> bool:
    """True only if a complaint marker appears OUTSIDE negation.

    "Ничего не болит, всё хорошо" must never read as a complaint —
    live fs-6e3abff0 escalated urgent on exactly this (false RED).
    Clause-scoped via shared safety guards.
    """
    from packages.safety.patterns import is_negated_at, split_clauses

    if is_urgent_concern(text):
        return True
    for clause in split_clauses((text or "").lower()):
        for match in _COMPLAINT_RE.finditer(clause):
            if not is_negated_at(clause, match.start()):
                return True
    return False


def _probe_duration(state: EngineState, text: str) -> ProbeStep:
    from packages.dialogue_engine.issue_memory import extract_grounded_onset_value
    from packages.dialogue_engine.state import CheckPath

    if is_urgent_concern(text) or is_urgent_concern(state.wellness_concern):
        state.check_path = CheckPath.URGENT
        state.probe_phase = None
        return ProbeStep(action=ProbeAction.URGENT_CLOSE)
    if not looks_like_duration_answer(text):
        return ProbeStep(action=ProbeAction.SPEAK_PROBE, probe_phase="duration")
    state.wellness_duration = text
    state.probe_phase = None
    if state.active_episode_id:
        ep = state.issue_episodes.get(state.active_episode_id)
        if ep is not None:
            duration = extract_grounded_onset_value(text)
            if duration:
                ep.known_attributes["duration"] = duration
            return ProbeStep(action=ProbeAction.CONTINUE_LADDER)
    next_slot = state.next_open_slot()
    return ProbeStep(
        action=ProbeAction.SPEAK_SLOT,
        next_slot=next_slot,
        ack_polarity="negative",
    )


def _probe_severity(state: EngineState, text: str) -> ProbeStep:
    from packages.dialogue_engine.issue_memory import (
        extract_grounded_severity_value,
        get_active_episode,
    )
    from packages.dialogue_engine.state import CheckPath

    # Emergency verbs hijack any probe phase — never ask severity on red.
    if is_urgent_concern(text) or is_urgent_concern(state.wellness_concern):
        state.check_path = CheckPath.URGENT
        state.probe_phase = None
        return ProbeStep(action=ProbeAction.URGENT_CLOSE)
    severity = extract_grounded_severity_value(text)
    if severity is not None:
        episode = get_active_episode(state)
        if episode is not None:
            episode.known_attributes["severity"] = severity
        state.observations["concern_severity"] = severity
        state.probe_phase = None
        return ProbeStep(action=ProbeAction.CONTINUE_LADDER)
    return ProbeStep(action=ProbeAction.SPEAK_PROBE, probe_phase="severity")


def _probe_pain_night(state: EngineState, text: str) -> ProbeStep:
    from packages.dialogue_engine.state import CheckPath

    # Emergency verbs hijack any probe phase — never ask plans on red signal.
    if is_urgent_concern(text) or is_urgent_concern(state.wellness_concern):
        state.check_path = CheckPath.URGENT
        state.probe_phase = None
        return ProbeStep(action=ProbeAction.URGENT_CLOSE)
    state.pain_at_night = text
    state.probe_phase = None
    return ProbeStep(action=ProbeAction.SPEAK_PLANS)


_register_probe("concern", _probe_concern)
_register_probe("duration", _probe_duration)
_register_probe("severity", _probe_severity)
_register_probe("pain_night", _probe_pain_night)


def advance_probe_phase(state: EngineState, text: str) -> ProbeStep:
    phase = state.probe_phase
    if not phase:
        return ProbeStep(action=ProbeAction.CONTINUE_LADDER)
    handler = _PROBE_FLOW.get(phase)
    if handler is None:
        state.probe_phase = None
        return ProbeStep(action=ProbeAction.CONTINUE_LADDER)
    return handler(state, text)


def symptom_followup_label(concern: str) -> str | None:
    text = concern or ""
    if _SYMPTOM_HEAD.search(text):
        return "головная боль"
    if _SYMPTOM_STOMACH.search(text):
        return "живот"
    if _SYMPTOM_BACK.search(text):
        return "спина"
    if _SYMPTOM_PRESSURE.search(text):
        return "давление"
    if has_pain_mention(text):
        return "самочувствие"
    return None


_FOLLOWUP_BY_SYMPTOM: dict[str, str] = {
    "head": "Прошлый раз вы говорили о головной боли. Как сейчас голова?",
    "живот": "Прошлый раз беспокоил живот. Как сейчас?",
    "спина": "Прошлый раз болела спина. Как сейчас?",
    "давление": "Прошлый раз вы говорили о давлении. Как сейчас?",
}


def _past_episode_labels(prior: dict[str, str]) -> list[str]:
    """Labels carried from the previous call's episode digest.

    Format written by build_call_metadata: `label@site:status | ...`.
    Returns speakable labels (label part only), up to the stored entries.
    Never raises on foreign/malformed values — garbage yields [].
    """
    raw = (prior.get("past_episodes") or "").strip()
    if not raw:
        return []
    labels: list[str] = []
    for chunk in raw.split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        label = chunk.split("@", 1)[0].strip().rstrip("., ")[:80]
        if label:
            labels.append(label)
    return labels


def prior_followup_question(prior: dict[str, str]) -> str | None:
    concern = (
        prior.get("wellness_concern")
        or prior.get("wellness_detail")
        or prior.get("symptom_followup")
        or ""
    ).strip()
    if not concern:
        # Episode digest carryover: the previous call may have grounded
        # episodes without a wellness_concern string (e.g. concern asked
        # but recorded on the episode only). First digest label speaks.
        _digested = _past_episode_labels(prior)
        if _digested:
            concern = _digested[0]
    if not concern:
        return None
    label = symptom_followup_label(concern) or concern
    if "голов" in label:
        return _FOLLOWUP_BY_SYMPTOM["head"]
    if label in _FOLLOWUP_BY_SYMPTOM:
        return _FOLLOWUP_BY_SYMPTOM[label]
    short = label[:60].rstrip("., ")
    return f"Прошлый раз вы говорили: {short}. Как сейчас себя чувствуете?"


def build_call_metadata(state: EngineState) -> dict[str, str]:
    from packages.dialogue_engine.state import CheckPath

    meta: dict[str, str] = {}
    if state.wellness_concern:
        meta["wellness_concern"] = state.wellness_concern
        label = symptom_followup_label(state.wellness_concern)
        if label:
            meta["symptom_followup"] = label
    if state.wellness_duration:
        meta["wellness_duration"] = state.wellness_duration
    if state.pain_at_night:
        meta["pain_at_night"] = state.pain_at_night
    if state.check_path != CheckPath.STANDARD:
        meta["check_path"] = state.check_path.value
    digest = episode_digest(state)
    if digest:
        meta["past_episodes"] = digest
    return meta


_BARE_VERB_LABELS = frozenset(
    {"болит", "боль", "ноет", "ломит", "давит", "беспокоит", "побаливает"}
)


def episode_digest(state: EngineState) -> str:
    """Compact carryover of this call's grounded episodes for the next call.

    Up to 2 speaker episodes as `label@site:status` joined by ` | `.
    String-only (snapshot metadata contract); someone else's complaints,
    bare verbs without a site, and empty labels are skipped — the next
    call must never inherit debris as biography. Read by
    prior_followup_question / past_site_matches; corroboration only, never
    a standalone fact.
    """
    parts: list[str] = []
    sited = any((ep.body_site or "").strip() for ep in state.issue_episodes.values())
    for ep in state.issue_episodes.values():
        if len(parts) >= 2:
            break
        if (ep.subject or "unknown") == "other_person":
            continue
        label = (ep.primary_label or "").strip().rstrip("., ")
        site = (ep.body_site or "").strip()
        if not label:
            continue
        if not site and label.lower() in _BARE_VERB_LABELS and sited:
            continue
        status = (ep.status or "open").strip() or "open"
        if status not in ("open", "suspended", "resolved"):
            status = "open"
        entry = f"{label[:80]}@{site[:40]}:{status}" if site else f"{label[:80]}:{status}"
        parts.append(entry)
    return " | ".join(parts)


def past_site_matches(
    prior: dict[str, str] | None, *, sites: set[str], labels: list[str]
) -> str | None:
    """Match grounded current mentions against the previous call's digest.

    Returns the matched past label, else None. Corroboration only: the
    caller must already hold a grounded current mention — a past entry
    alone never fires. Used to mark `past_episode_reopened` instead of
    interrogating a returning complaint as brand new.
    """
    if not prior:
        return None
    entries = (prior.get("past_episodes") or "").strip()
    if not entries:
        return None
    cur_sites = {s.strip().lower() for s in sites if (s or "").strip()}
    cur_labels = [lb.strip().lower() for lb in labels if (lb or "").strip()]
    for chunk in entries.split("|"):
        chunk = chunk.strip().lower()
        if not chunk:
            continue
        head = chunk.split("@", 1)[0].strip()
        site = ""
        if "@" in chunk:
            site = chunk.split("@", 1)[1].split(":", 1)[0].strip()
        if site and site in cur_sites:
            return chunk.split("@", 1)[0].strip() or None
        for cl in cur_labels:
            if head and (head in cl or cl in head):
                return chunk.split("@", 1)[0].strip() or None
    return None
