"""Question copy for pilot daily-check slots."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.dialogue_engine.state import EngineState

_SLOT_QUESTIONS: dict[str, str] = {
    "wellness": "Как вы себя чувствуете?",
    "mood": "А какое у вас сегодня настроение?",
    "sleep": "Как вы спали?",
    "plans": "Какие у вас планы на сегодня?",
}

# Variety pools: index 0 is ALWAYS the canonical text above (stable default,
# tests pin it via IMVERA_SPEECH_DAY). Live rotation picks by day ordinal —
# same day same phrasing (redials consistent), new day new phrasing.
# Deterministic: differential/corpus see identical picks on both sides.
_SLOT_QUESTION_VARIANTS: dict[str, list[str]] = {
    "wellness": [
        "Как вы себя чувствуете?",
        "Как ваше самочувствие сегодня?",
        "Как себя чувствуете — всё нормально?",
        "Самочувствие сегодня как?",
        "Как себя чувствуете сегодня?",
        "Всё хорошо у вас сегодня?",
    ],
    "mood": [
        "А какое у вас сегодня настроение?",
        "Настроение сегодня как?",
        "Как настроение?",
        "Настроение как сегодня?",
        "Как настрой сегодня?",
        "Настроение как?",
    ],
    "sleep": [
        "Как вы спали?",
        "Как спалось сегодня?",
        "Ночью как спали — выспались?",
        "Спали хорошо?",
        "Как ночь прошла — спали?",
        "Выспались сегодня?",
    ],
    "plans": [
        "Какие у вас планы на сегодня?",
        "Что сегодня планируете?",
        "Чем сегодня займётесь?",
        "На день планы есть?",
        "Что на сегодня запланировали?",
        "День как проведёте?",
    ],
}

_PROBE_QUESTION_VARIANTS: dict[str, list[str]] = {
    "concern": [
        "Что именно беспокоит?",
        "Что вас беспокоит сильнее всего?",
        "На что жалуетесь?",
        "Что-то беспокоит?",
        "Где болит или что тревожит?",
        "Жалобы есть какие?",
    ],
    "duration": [
        "Как давно это продолжается?",
        "Как давно началось?",
        "Давно это у вас?",
        "Когда началось?",
        "Давно болит?",
        "Сколько уже продолжается?",
    ],
    "severity": [
        "Насколько сильная боль?",
        "Боль сильная или терпимая?",
        "Сейчас это сильно беспокоит или терпимо?",
        "Сильно болит?",
        "Терпимо или сильно?",
        "Боль насколько сильная?",
    ],
    "pain_night": [
        "А ночью не болело?",
        "Ночью как — болело или спокойно?",
        "А ночью беспокоит?",
        "Ночью болело?",
        "Спать не мешало?",
        "Ночь спокойно прошла?",
    ],
}

_ITS_VARIANTS: tuple[tuple[str, str], ...] = (
    ("Поняла вас.", "А кроме этого — по самочувствию ничего не тревожит?"),
    ("Поняла вас.", "Может, ещё что-то важное хотите рассказать — по здоровью или дома?"),
    ("Записала.", "Подскажите, есть ли ещё что-то важное по здоровью или дома?"),
    ("Поняла.", "Что-то ещё важное есть?"),
    ("Записала.", "Ещё что-то беспокоит?"),
    ("Хорошо.", "Что-то ещё хотите сказать?"),
)
# The spoken shape of the same bank (acknowledgement + question), kept for the
# speech-discipline scanners. The pair above stays the single source of truth.
_ITS_QUESTION_VARIANTS: tuple[str, ...] = tuple(
    f"{ack} {question}" for ack, question in _ITS_VARIANTS
)


def _speech_day() -> int:
    """Day ordinal driving rotation. IMVERA_SPEECH_DAY pins it in tests."""
    import os
    from datetime import date

    raw = (os.environ.get("IMVERA_SPEECH_DAY", "") or "").strip()
    if raw.lstrip("-").isdigit():
        return int(raw)
    return date.today().toordinal()


def _rotate(pool: list[str] | tuple[str, ...]) -> str:
    return pool[_speech_day() % len(pool)]


def rotate_pool(
    state: EngineState | None, key: str, pool: list[str] | tuple[str, ...]
) -> str:
    """Per-call rotation seeded by day AND call: the seed mixes the day
    ordinal with the call id, so different calls (even the same day) open
    on different variants, while repeats within a call still advance.
    Stateless direct calls keep legacy day rotation (unit tests pin it).
    """
    if state is None:
        return _rotate(pool)
    import zlib

    seed = (_speech_day() + zlib.crc32((state.call_id or "").encode())) % len(pool)
    counters = state.pool_counters
    idx = counters.get(key, seed)
    counters[key] = (idx + 1) % len(pool)
    return pool[idx]

_PROBE_QUESTIONS: dict[str, str] = {
    "concern": "Что именно беспокоит?",
    "duration": "Как давно это продолжается?",
    "severity": "Насколько сильная боль?",
    "pain_night": "А ночью не болело?",
}

_TOPIC_QUESTIONS: dict[str, str] = {
    "topic_sleep_pattern": "Что ночью мешало спать?",
    "topic_sleep_daytime_impact": "А днём как — есть усталость?",
    "topic_abdominal_pain_current": "А сейчас живот ещё беспокоит?",
    "topic_abdominal_pain_onset": "Как давно это началось?",
    "topic_headache_onset": "Как давно болит голова?",
    "topic_headache_severity": "Боль сильная или терпимая?",
    "topic_limb_pain_onset": "Как давно это беспокоит?",
    "topic_limb_pain_function": "Мешает ли это ходить или двигаться?",
    "topic_mood_loneliness_intensity": "Насколько тяжело на душе сегодня?",
    "topic_mood_loneliness_social": "Было ли с кем поговорить?",
    "topic_medication_status_today": "Принимали ли сегодня лекарства?",
    "topic_general_symptom_concern": "Что именно беспокоит?",
    "topic_general_symptom_duration": "Как давно это продолжается?",
}

# Backchannel acks (rotating bank, Step 4: speech lives in banks).
BACKCHANNEL_ACKS: tuple[str, ...] = (
    "Слушаю вас.",
    "Да-да, слушаю вас.",
    "Да, слушаю вас.",
    "Слушаю внимательно.",
)

# Greeting back-ack (singleton by design: one fixed hello, no rotation).
GREETING_ACK = "Здравствуйте! Я вас слушаю."

_SLOT_CLARIFICATIONS: dict[str, str] = {
    "wellness": "Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.",
    "mood": "Как у вас настроение — хотя бы коротко?",
    "sleep": "Как вы спали — коротко, пожалуйста?",
    "plans": "Какие у вас планы на сегодня — в двух словах?",
    "probe_concern": "Расскажите коротко, что именно беспокоит.",
    "probe_duration": "Как давно это длится — хотя бы примерно?",
    "probe_severity": "Насколько сильная боль — сильная или терпимая?",
    "probe_pain_night": "А ночью было больно или спокойно?",
    "important_to_share": "Простите, не разобрала — есть ли ещё что-то важное?",
}

# Re-ask variants: index 0 is always the canonical text above (byte-stable
# first ask). Later attempts rotate — no identical repeats within a call.
_SLOT_CLARIFICATION_TAILS: dict[str, list[str]] = {
    "wellness": ["", "Попробуйте иначе: хорошо, нормально или плохо?"],
    "mood": ["", "Одним словом: хорошее или плохое?"],
    "sleep": ["", "С уточнением: хорошо спали или плохо?"],
    "plans": ["", "Например: дома, гуляете, к врачу?"],
    "probe_concern": ["", "Опишите своими словами, что чувствуете."],
    "probe_duration": ["", "Хотя бы примерно: сегодня, вчера, давно?"],
    "probe_pain_night": ["", "Так было больно или нет?"],
}

# Ack tails appended after the canonical ack, rotated by turn_seq.
# Index 0 is "" (bare canonical) so default/short calls stay identical.
# Content tails are MANDATORY (never bare): a standalone «Хорошо.» /
# «Понятно.» as a whole response is the tic the speech-discipline gate
# forbids. Index 0 is the default, so it carries content too.
_WELLNESS_ACK_TAILS: dict[str, list[str]] = {
    "negative": [
        "Я вас внимательно слушаю.",
        "Спасибо, что рассказали.",
        "Давайте разберёмся по порядку.",
    ],
    "uncertain": [
        "Я запишу это.",
        "Спасибо, что сказали.",
        "Я вас слушаю.",
    ],
    "positive": ["Рада за вас.", "Очень хорошо.", "Ну и славно."],
    "neutral": ["Спасибо, что рассказали.", "Спасибо, что сказали.", "Я вас слушаю."],
}

_REPAIR_ACK = "Да, слышу."
# Neutral receipt before a clarifying re-ask. Lives in the bank so the reducer
# and the policy never hardcode it (phrase-discipline gate), and so the
# renderer may replace it with a grounded reaction.
CLARIFY_ACK = "Понимаю."
_PARTIAL_CLOSE = "Сейчас не получилось узнать, как у вас дела. До свидания."
# Partial close when facts WERE learned: claiming «не получилось» would be
# a lie the elder hears (live: three positive answers followed by «не
# получилось»). Same hangup semantics, honest wording.
_PARTIAL_CLOSE_WITH_FACTS = "Спасибо, всё записала. До свидания."
_WRONG_PERSON_FINAL = "Извините, видимо, ошибились номером. До свидания."
_DEFER_FINAL = "Поняла. Поговорим в другой раз. До свидания."
_REVOKE_FINAL = "Поняла, больше не буду звонить без вашего согласия. До свидания."
_PAUSE_ACK = "Хорошо, подожду."
_GOODBYE_CONFIRM = "Вы хотите закончить разговор?"
_GOODBYE_FINAL = "До свидания. Хорошего дня."
_GOODBYE_MARKERS = ("до свидания", "всего доброго")
_WELLNESS_ACK_GOOD = "Рада это слышать."
_WELLNESS_ACK_NORMAL = "Понятно."
_WELLNESS_ACK_OKAY = "Хорошо, поняла."
_WELLNESS_ACK_UNCERTAIN = "Понимаю."
_WELLNESS_ACK_NEGATIVE = "Мне жаль это слышать."
# Episode acknowledgment keyed by MEANING (what happened), not by situation
# phrase. Small by design — PhraseSelect discipline, not bank inflation: a
# new wording must not become a new branch in policy.
_EPISODE_ACK: dict[str, tuple[str, ...]] = {
    # A symptom the elder just reported for the first time.
    "new": (
        "{label} — очень жаль, что беспокоит.",
        "{label} — сочувствую, всё записываю.",
        "{label} — поняла, это неприятно.",
    ),
    # An answer to the question Vera just asked.
    "answer": (
        "{label} — спасибо, что рассказали.",
        "{label} — записала, спасибо.",
        "{label} — поняла вас, записала.",
    ),
    # The elder already said it hurts badly.
    "strong": (
        "{label} — как же тяжело, сочувствую.",
        "{label} — понимаю, терпеть такое трудно.",
        "{label} — сильно, я рядом, слушаю.",
    ),
    # Reported as easing or gone.
    "improving": (
        "{label} — полегчало, рада за вас.",
        "{label} — проходит, очень хорошо.",
    ),
}
# Legacy constant — prefer summary_close_speech(state).
_SUMMARY_TEXT = "Всё, спасибо. Всего вам хорошего. До свидания."
_URGENT_CLOSE = (
    "Понимаю, это важно. Я передам информацию близким. "
    "Спасибо за разговор. До свидания."
)
_ANSWER_WAIT_MS = 7000
# Neutral by default: the legacy "Хорошо." prefix lied after "Пло."/UNCLEAR
# (wellness OPEN, live fs-41e2a57b). Positive ack lives in wellness_ack();
# the ITS transition itself must never assert a polarity it did not measure.
_IMPORTANT_TO_SHARE_QUESTION = (
    "Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии "
    "или дома, на что мне стоит обратить внимание?"
)
# Phone-spoken brand. Latin «IMVERA» is skipped/garbled by Russian Silero TTS.
# Pronunciation: Амвера (not «им вера»).
_SERVICE_SPOKEN_NAME = "Амвера"


def service_spoken_name() -> str:
    return _SERVICE_SPOKEN_NAME


def concern_summary_phrase(state: EngineState) -> str:
    """Short spoken list of what Vera heard — for warmer goodbye."""
    from packages.dialogue_engine.issue_memory import clinical_issue_concept

    bits: list[str] = []
    seen: set[str] = set()
    eps = list(state.issue_episodes.values())
    # Bare-verb labels («болит», «беспокоит» from STT debris) are dropped
    # when a sited episode says the same thing (live fe57cba6 listed both).
    _sited = any((ep.body_site or "").strip() for ep in eps)
    _BARE_VERBS = frozenset(
        {"болит", "боль", "ноет", "ломит", "давит", "беспокоит", "побаливает"}
    )
    for ep in eps:
        # Someone else's complaint is not the speaker's symptom list.
        if (ep.subject or "unknown") != "speaker":
            continue
        label = (ep.primary_label or "").strip().lower()
        site = (ep.body_site or "").strip().lower()
        # Deduplicate a restated symptom, not every symptom at that site.
        concept = clinical_issue_concept(label, ep.canonical_key)
        site_key = f"{site}:{concept}" if site else None
        if site_key and site_key in seen:
            continue
        key = site_key or label
        if not key or key in seen:
            continue
        seen.add(key)
        if site_key:
            seen.add(site_key)
        if not site and label in _BARE_VERBS and _sited:
            continue
        if "круж" in label or ep.kind == "dizziness":
            bits.append("головокружение")
        elif concept == "pain" and (site == "голова" or "голов" in label):
            bits.append("головная боль")
        elif concept == "pain" and (site == "живот" or "живот" in label):
            bits.append("боль в животе")
        elif "тошн" in label:
            bits.append("тошнота")
        elif ep.kind == "sleep_problem" or "сон" in label or "спал" in label:
            bits.append("плохой сон")
        elif label:
            bits.append(label)
        for m in ep.mentions:
            ml = (m.label or "").lower()
            if "тошн" in ml and "тошнота" not in bits:
                bits.append("тошнота")
            # Different symptoms at the same site are not duplicate pain.
            # Keep the literal tremor report in the spoken recap too.
            if ("тряс" in ml or "дрож" in ml) and ml not in bits:
                bits.append(ml)
    if not bits:
        return ""
    if len(bits) == 1:
        return bits[0]
    if len(bits) == 2:
        return f"{bits[0]} и {bits[1]}"
    return f"{', '.join(bits[:-1])} и {bits[-1]}"


def summary_close_speech(
    state: EngineState,
    *,
    acknowledge: str = "",
) -> str:
    """Warm close: записала + На сегодня всё + Берегите себя.

    No farewell here — the single goodbye belongs to goodbye_final.
    """
    name = (state.elder_display_name or "").strip()
    concerns = concern_summary_phrase(state)
    ack = acknowledge.strip()
    next_hint = (state.prior_call_context or {}).get("next_call_spoken", "").strip()

    if concerns:
        if name:
            core = (
                f"Спасибо, {name}. Я записала: {concerns}. "
                "На сегодня всё. Берегите себя."
            )
        else:
            core = (
                f"Спасибо. Я записала: {concerns}. "
                "На сегодня всё. Берегите себя."
            )
    elif name:
        core = (
            f"Спасибо, {name}. На сегодня всё. "
            "Берегите себя."
        )
    else:
        core = "Спасибо. На сегодня всё. Берегите себя."

    if next_hint and "записала" not in core.lower():
        if name:
            core = (
                f"Спасибо, {name}. {next_hint} "
                "На сегодня всё. Берегите себя."
            )
        else:
            core = (
                f"Спасибо. {next_hint} "
                "На сегодня всё. Берегите себя."
            )
    if ack:
        if ack.startswith("Спасибо"):
            thanks = f"Спасибо, {name}. " if name else "Спасибо. "
            core = core.removeprefix(thanks)
        return f"{ack} {core}"
    return core


def goodbye_final_speech(state: EngineState) -> str:
    name = (state.elder_display_name or "").strip()
    if name:
        return f"До свидания, {name}. Всего вам хорошего."
    return _GOODBYE_FINAL


def episode_ack(
    kind: str, label: str, *, turn_seq: int = 0,
    conversational: bool = False, additional_labels: tuple[str, ...] = (),
    clarifying: bool = True,
) -> str:
    """Acknowledgment for a grounded episode fact, chosen by meaning.

    Falls back to the neutral form for an unknown signal — never invents a
    branch of its own.
    """
    if conversational and kind in ("new", "answer"):
        clauses = [_complaint_clause(item) for item in (label, *additional_labels)]
        if len(clauses) > 1 and not all(clauses):
            # Literal grounded labels remain speakable even when a predicate
            # has no grammar projection. Never rename dizziness as pain.
            labels = list(dict.fromkeys(item.lower() for item in (label, *additional_labels)))
            tail = " Давайте по порядку." if clarifying else ""
            joined = ", ".join(labels[:-1]) + " и " + labels[-1]
            return f"Слышу вас: {joined}.{tail}"
        if all(clauses):
            unique = list(dict.fromkeys(clauses))
            if len(unique) > 1:
                joined = ", ".join(unique[:-1]) + " и " + unique[-1]
                tail = " Давайте по порядку." if clarifying else ""
                return f"Понимаю, {joined}.{tail}"
            if re.search(r"\b(болит|болят|ноет|ноют|ломит|ломят)\b", unique[0]):
                return f"Жаль, что {unique[0]}."
            return f"Слышу, {unique[0]}."
    pool = _EPISODE_ACK.get(kind)
    if not pool:
        return f"Поняла вас. {label} — зафиксировала."
    template = pool[turn_seq % len(pool)] if turn_seq else pool[0]
    return template.format(label=label)


def reported_symptoms_ack(labels: tuple[str, ...]) -> str:
    """Quote accepted past/uncertain-time reports without claiming current pain or relief."""
    unique = list(dict.fromkeys(label.strip().lower().rstrip(".!?") for label in labels if label))
    return f"Слышу вас: {' и '.join(unique)}." if unique else ""


def current_relief_ack() -> str:
    return "Рада, что сейчас вам легче."


def shared_information_ack() -> str:
    return "Спасибо, что рассказали."


def strong_pain_transition(site: str, kind: str, label: str) -> str:
    return f"Понимаю, сильная боль — это тяжело. {episode_transition(site, kind, label)}"


def thread_followup(hook: str) -> str:
    return f"Вы говорили: «{hook}». Я вас слушаю. Хотите рассказать чуть подробнее?"


def thread_continuation() -> str:
    return "Как вам сейчас, когда вы об этом рассказываете?"


def thread_listener_ack() -> str:
    return "Слушаю вас."


def thread_return_ack() -> str:
    return "Спасибо, что поделились."


def thread_wellness_return() -> str:
    return "А как ваше самочувствие сегодня?"


def _complaint_clause(label: str) -> str:
    """Grammar projection of a grounded label; never infer another symptom."""
    normalized = label.strip().lower().rstrip(".!?")
    canonical = {
        "головная боль": "голова болит",
        "боль в животе": "живот болит",
        "тошнота": "тошнит",
        "головокружение": "кружится голова",
    }
    if normalized in canonical:
        return canonical[normalized]
    if re.search(
        r"\b(болит|болят|ноет|ноют|ломит|ломят|трясётся|трясется|"
        r"трясутся|дрожит|дрожат|тошнит)\b", normalized,
    ):
        return normalized
    return ""


def temporal_answer_ack(value: str) -> str:
    return f"Поняла, это продолжается уже {value.lower()}."


def severity_answer_ack(*, strong: bool, pain: bool = True) -> str:
    if strong:
        return ("Сочувствую, сильную боль тяжело переносить." if pain
                else "Сочувствую, это тяжело переносить.")
    return "Поняла, сейчас терпимо."


def requests_question_explanation(text: str) -> bool:
    """A delivery distinction inside accepted REPAIR, not a new dialogue act."""
    return bool(re.search(
        r"\b(уточни\w*|конкрет\w*|не\s+понял\w*|не\s+понимаю|что\s+значит)\b", text, re.I,
    ))


def explain_episode_question(label: str, question: str, *, attribute: str = "") -> str:
    if label.strip().lower() == "головная боль":
        if attribute == "severity":
            return "Я спрашиваю про головную боль. Её можно терпеть или она очень сильная?"
        return f"Я спрашиваю про головную боль. {question}"
    if attribute == "severity":
        return f"Уточню про {label.lower()}. Это можно терпеть или очень тяжело переносить?"
    return f"Уточню вопрос. {question}"


def episode_transition(site: str, kind: str, label: str = "") -> str:
    if not label:
        # No grounded topic to name: retain the existing bare-label contract.
        return "Хорошо."
    topics = {
        "голова": "головную боль", "живот": "боль в животе",
        "рука": "руки", "нога": "ноги",
    }
    if site in ("голова", "живот") and not re.search(
        r"\b(боль|болит|болят|ноет|ноют)\b", label.lower(),
    ):
        topics.pop(site)
    topic = "сон" if kind == "sleep_problem" else topics.get(site)
    if topic:
        return f"Теперь про {topic}."
    return f"{label[0].upper() + label[1:]} — давайте уточним."


def requested_episode_ack(site: str, kind: str, label: str) -> str:
    transition = episode_transition(site, kind, label)
    if transition.startswith("Теперь про "):
        return "Хорошо, сначала про " + transition.removeprefix("Теперь про ")
    return "Хорошо. " + transition


def without_listener_prefix(text: str) -> str:
    """Remove only a redundant acknowledgment, keeping the question intact."""
    return re.sub(r"^(Поняла вас|Поняла|Записала|Хорошо)\.\s*", "", text)


def its_question_and_ack(state: EngineState | None = None) -> tuple[str, str]:
    """The ITS transition acknowledgement and its question, chosen together.

    Returned separately because the renderer owns the spoken surface and may
    replace a content-free transition with a grounded reaction. The pair is
    taken from the same rotated variant, and the pool advances exactly once.
    """
    ack, question = rotate_pool(state, "its", _ITS_VARIANTS)
    return ack, question


def important_to_share_question(state: EngineState | None = None) -> str:
    """The ITS question alone (no transition acknowledgement)."""
    return its_question_and_ack(state)[1]


def topic_question(intent: str) -> str:
    return _TOPIC_QUESTIONS.get(intent, "Расскажите, пожалуйста, чуть подробнее.")


def probe_question(
    phase: str, *, clarification: bool = False, state: EngineState | None = None
) -> str:
    key = f"probe_{phase}"
    if clarification:
        return _SLOT_CLARIFICATIONS.get(key, _PROBE_QUESTIONS.get(phase, "Повторите, пожалуйста."))
    pool = _PROBE_QUESTION_VARIANTS.get(phase)
    if pool:
        return rotate_pool(state, key, pool)
    return _PROBE_QUESTIONS.get(phase, "Расскажите, пожалуйста.")


def plans_question(state: EngineState | None = None) -> str:
    if state is None:
        return _SLOT_QUESTIONS["plans"]
    concern = (state.wellness_concern or "").lower()
    if "голов" in concern:
        return "При головной боли лучше не напрягаться. Какие у вас планы на сегодня?"
    if state.pain_at_night and any(
        x in (state.pain_at_night or "").lower() for x in ("да", "бол", "плох", "не сп")
    ):
        return "Надеюсь, днём будет легче. Чем планируете заняться сегодня?"
    if state.check_path.value == "pain_short":
        return "Чем хотите заняться сегодня, если позволит самочувствие?"
    if state.wellness_concern:
        return "С учётом самочувствия, какие у вас планы на сегодня?"
    return _SLOT_QUESTIONS["plans"]


def wellness_ack(
    *, polarity: str | None = None, value: str = "", turn_seq: int = 0
) -> str:
    """Short ack after wellness slot fill — polarity-aware.

    Always content-carrying: the tail is mandatory, never bare. Rotation is
    by turn_seq over content tails (speech-discipline gate forbids
    standalone «Хорошо.»/«Понятно.» as whole responses).
    """
    from packages.dialogue_engine.fast_interpreter import _detect_polarity, _normalize_core

    pol = polarity or _detect_polarity(value)
    core = _normalize_core(value)
    if pol == "negative":
        base = _WELLNESS_ACK_NEGATIVE
        tails = _WELLNESS_ACK_TAILS["negative"]
    elif pol == "uncertain" or re.match(
        r"^(так\s+себе|сойд[её]т|пойд[её]t|средн\w*|терпимо|ну\s+такое)\.?$", core, re.I
    ):
        base = _WELLNESS_ACK_UNCERTAIN
        tails = _WELLNESS_ACK_TAILS["uncertain"]
    elif re.match(r"^(пойд[её]т|терпимо|более-менее)\.?$", core, re.I):
        base = _WELLNESS_ACK_OKAY
        tails = _WELLNESS_ACK_TAILS["positive"]
    else:
        normal_short = re.match(r"^(нормально|обычно|ничего|обычное)\.?$", core, re.I)
        if normal_short or "нормально" in value.lower():
            base = _WELLNESS_ACK_NORMAL
            tails = _WELLNESS_ACK_TAILS["neutral"]
        elif pol == "positive":
            base = _WELLNESS_ACK_GOOD
            tails = _WELLNESS_ACK_TAILS["positive"]
        else:
            base = _WELLNESS_ACK_UNCERTAIN
            tails = _WELLNESS_ACK_TAILS["neutral"]
    if base == _WELLNESS_ACK_GOOD:
        return base
    tail = tails[turn_seq % len(tails)]
    return f"{base} {tail}".strip()


def not_recalled_ack() -> str:
    """A discharged unknown is respected, never medical reassurance."""
    return "Понимаю, не будем угадывать."


def mission_resume_ack() -> str:
    """Explain an actual planner transition; do not infer symptom recovery."""
    return "Вернёмся к моему вопросу."


def opening_speech(elder_display_name: str, prior_context: dict[str, str] | None = None) -> str:
    from packages.dialogue_engine.check_path import prior_followup_question

    name = (elder_display_name or "").strip() or "вас"
    brand = _SERVICE_SPOKEN_NAME
    follow = prior_followup_question(prior_context or {})
    if follow:
        q = follow[0].lower() + follow[1:] if follow and follow[0].isupper() else follow
        return f"Здравствуйте. Это сервис {brand}. {name}, {q}"
    wellness = _rotate(_SLOT_QUESTION_VARIANTS["wellness"])
    wellness = wellness[0].lower() + wellness[1:] if wellness else wellness
    hello, intro = _greeting_parts()
    return f"{hello}. {intro}. {name}, {wellness}"


def _greeting_parts() -> tuple[str, str]:
    """Time-of-day greeting + alternate intro on odd days. Same day = same
    greeting (redials consistent). System tz = lab Mac (Moscow)."""
    import os
    from datetime import datetime

    raw = (os.environ.get("IMVERA_SPEECH_DAY", "") or "").strip()
    now = datetime.now()
    day = int(raw) if raw.lstrip("-").isdigit() else now.toordinal()
    brand = _SERVICE_SPOKEN_NAME
    intro = f"Это Вера из сервиса {brand}" if day % 2 == 1 else f"Это сервис {brand}"
    hour_raw = (os.environ.get("IMVERA_SPEECH_HOUR", "") or "").strip()
    hour = int(hour_raw) if hour_raw.lstrip("-").isdigit() else now.hour
    if 5 <= hour <= 10:
        return "Доброе утро", intro
    if 18 <= hour <= 23:
        return "Добрый вечер", intro
    return "Здравствуйте", intro


def _clarification_attempt(state: EngineState | None, slot: str) -> int:
    """Attempt index for clarification variety. First clarification keeps
    the canonical text (index 0); later ones rotate. Backward compatible
    by construction."""
    if state is None:
        return 0
    goal = state.goals.get(slot)
    if goal is None:
        return 0
    return max(0, int(goal.delivered_attempts) - 1)


def slot_question(
    slot: str,
    *,
    clarification: bool = False,
    state: EngineState | None = None,
) -> str:
    if slot == "plans":
        if clarification:
            base = _SLOT_CLARIFICATIONS["plans"]
            tails = _SLOT_CLARIFICATION_TAILS.get("plans", [""])
            tail = tails[_clarification_attempt(state, slot) % len(tails)]
            return f"{base} {tail}".strip() if tail else base
        return plans_question(state)
    if clarification:
        base = _SLOT_CLARIFICATIONS.get(slot, "Повторите, пожалуйста, коротко.")
        tails = _SLOT_CLARIFICATION_TAILS.get(slot)
        if not tails:
            return base
        tail = tails[_clarification_attempt(state, slot) % len(tails)]
        return f"{base} {tail}".strip() if tail else base
    if slot.startswith("probe_"):
        return probe_question(slot.removeprefix("probe_"), state=state)
    if slot.startswith("episode_") or slot.startswith("topic_"):
        return "Расскажите, пожалуйста, чуть подробнее."
    pool = _SLOT_QUESTION_VARIANTS.get(slot)
    if pool:
        return rotate_pool(state, f"slot:{slot}", pool)
    return _SLOT_QUESTIONS.get(slot, "Повторите, пожалуйста, коротко.")


def repair_response(delivered_text: str, *, explanation: bool = False) -> str:
    if explanation:
        return _repeat_question(delivered_text)
    return f"{_REPAIR_ACK} {_repeat_question(delivered_text)}"




def _repeat_question(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "Повторите, пожалуйста."
    if stripped.endswith("?"):
        return stripped
    return f"Я спросила: {stripped}"
