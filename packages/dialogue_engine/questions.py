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
    ],
    "mood": [
        "А какое у вас сегодня настроение?",
        "Настроение сегодня как?",
        "Как настроение — ничего не тревожит?",
    ],
    "sleep": [
        "Как вы спали?",
        "Как спалось сегодня?",
        "Ночью как спали — выспались?",
    ],
    "plans": [
        "Какие у вас планы на сегодня?",
        "Что сегодня планируете?",
        "Чем сегодня займётесь?",
    ],
}

_PROBE_QUESTION_VARIANTS: dict[str, list[str]] = {
    "concern": [
        "Что именно беспокоит?",
        "Что вас беспокоит сильнее всего?",
        "На что жалуетесь?",
    ],
    "duration": [
        "Как давно это продолжается?",
        "Как давно началось?",
        "Давно это у вас?",
    ],
    "pain_night": [
        "А ночью не болело?",
        "Ночью как — болело или спокойно?",
        "А ночью беспокоит?",
    ],
}

_ITS_QUESTION_VARIANTS: tuple[str, ...] = (
    "Поняла вас. Есть ли сейчас ещё что-то важное в вашем самочувствии "
    "или дома, на что мне стоит обратить внимание?",
    "Поняла вас. А кроме этого — есть ли ещё что-то важное, о чём мне стоит знать?",
    "Записала. Подскажите, есть ли ещё что-то важное по здоровью или дома?",
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

_PROBE_QUESTIONS: dict[str, str] = {
    "concern": "Что именно беспокоит?",
    "duration": "Как давно это продолжается?",
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

_SLOT_CLARIFICATIONS: dict[str, str] = {
    "wellness": "Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.",
    "mood": "Как у вас настроение — хотя бы коротко?",
    "sleep": "Как вы спали — коротко, пожалуйста?",
    "plans": "Какие у вас планы на сегодня — в двух словах?",
    "probe_concern": "Расскажите коротко, что именно беспокоит.",
    "probe_duration": "Как давно это длится — хотя бы примерно?",
    "probe_pain_night": "А ночью было больно или спокойно?",
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
_WELLNESS_ACK_TAILS: dict[str, list[str]] = {
    "negative": ["", "Я вас внимательно слушаю.", "Расскажите, что беспокоит сильнее всего."],
    "uncertain": ["", "Я запишу это.", "Уточните чуть подробнее, пожалуйста."],
    "positive": ["", "Очень хорошо.", "Рада за вас."],
}

_REPAIR_ACK = "Да, слышу."
_PARTIAL_CLOSE = "Сейчас не получилось узнать, как у вас дела. До свидания."
_WRONG_PERSON_FINAL = "Извините, видимо, ошибились номером. До свидания."
_DEFER_FINAL = "Поняла. Поговорим в другой раз. До свидания."
_REVOKE_FINAL = "Поняла, больше не буду звонить без вашего согласия. До свидания."
_PAUSE_ACK = "Хорошо, подожду."
_GOODBYE_CONFIRM = "Вы хотите закончить разговор?"
_GOODBYE_FINAL = "До свидания. Хорошего дня."
_GOODBYE_MARKERS = ("до свидания", "всего доброго")
_WELLNESS_ACK = "Хорошо."
_WELLNESS_ACK_GOOD = "Рада это слышать."
_WELLNESS_ACK_NORMAL = "Понятно."
_WELLNESS_ACK_OKAY = "Хорошо, поняла."
_WELLNESS_ACK_UNCERTAIN = "Понимаю."
_WELLNESS_ACK_NEGATIVE = "Мне жаль это слышать."
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
        if (ep.subject or "unknown") == "other_person":
            continue
        label = (ep.primary_label or "").strip().lower()
        site = (ep.body_site or "").strip().lower()
        # Same-site dupes («голова болела» + «головная боль») list once.
        site_key = site or None
        if site_key and site_key in seen:
            continue
        key = site or label
        if not key or key in seen:
            continue
        seen.add(key)
        if site_key:
            seen.add(site_key)
        if not site and label in _BARE_VERBS and _sited:
            continue
        if "круж" in label or ep.kind == "dizziness":
            bits.append("головокружение")
        elif site == "голова" or "голов" in label:
            bits.append("головная боль")
        elif site == "живот" or "живот" in label:
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
    """Warm terminal close — MVP tone: записала + На сегодня всё + Берегите себя."""
    name = (state.elder_display_name or "").strip()
    concerns = concern_summary_phrase(state)
    ack = acknowledge.strip()
    next_hint = (state.prior_call_context or {}).get("next_call_spoken", "").strip()

    if concerns:
        if name:
            core = (
                f"Спасибо, {name}. Я записала: сегодня беспокоили {concerns}. "
                "На сегодня всё. Берегите себя. До свидания."
            )
        else:
            core = (
                f"Спасибо. Я записала: сегодня беспокоили {concerns}. "
                "На сегодня всё. Берегите себя. До свидания."
            )
    elif name:
        core = (
            f"Спасибо, {name}. На сегодня всё. "
            "Берегите себя. До свидания."
        )
    else:
        core = "Спасибо. На сегодня всё. Берегите себя. До свидания."

    if next_hint and "записала" not in core.lower():
        if name:
            core = (
                f"Спасибо, {name}. {next_hint} "
                "На сегодня всё. Берегите себя. До свидания."
            )
        else:
            core = (
                f"Спасибо. {next_hint} "
                "На сегодня всё. Берегите себя. До свидания."
            )
    if ack:
        return f"{ack} {core}"
    return core


def goodbye_final_speech(state: EngineState) -> str:
    name = (state.elder_display_name or "").strip()
    if name:
        return f"До свидания, {name}. Всего вам хорошего."
    return _GOODBYE_FINAL


def important_to_share_question() -> str:
    return _rotate(_ITS_QUESTION_VARIANTS)


def topic_question(intent: str) -> str:
    return _TOPIC_QUESTIONS.get(intent, "Расскажите, пожалуйста, чуть подробнее.")


def probe_question(phase: str, *, clarification: bool = False) -> str:
    key = f"probe_{phase}"
    if clarification:
        return _SLOT_CLARIFICATIONS.get(key, _PROBE_QUESTIONS.get(phase, "Повторите, пожалуйста."))
    pool = _PROBE_QUESTION_VARIANTS.get(phase)
    if pool:
        return _rotate(pool)
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

    turn_seq rotates an appended tail (index 0 = bare canonical, so
    default calls stay byte-identical).
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
        elif pol == "positive":
            base = _WELLNESS_ACK_GOOD
        else:
            base = _WELLNESS_ACK
        tails = _WELLNESS_ACK_TAILS["positive"]
    tail = tails[turn_seq % len(tails)] if turn_seq > 0 else ""
    return f"{base} {tail}".strip() if tail else base


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
    hour = now.hour
    if 5 <= hour <= 10:
        return "Доброе утро", intro
    if 18 <= hour <= 22:
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
        return probe_question(slot.removeprefix("probe_"))
    if slot.startswith("episode_") or slot.startswith("topic_"):
        return "Расскажите, пожалуйста, чуть подробнее."
    pool = _SLOT_QUESTION_VARIANTS.get(slot)
    if pool:
        return _rotate(pool)
    return _SLOT_QUESTIONS.get(slot, "Повторите, пожалуйста, коротко.")


def repair_response(delivered_text: str) -> str:
    return f"{_REPAIR_ACK} {_repeat_question(delivered_text)}"




def _repeat_question(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "Повторите, пожалуйста."
    if stripped.endswith("?"):
        return stripped
    return f"Я спросила: {stripped}"
