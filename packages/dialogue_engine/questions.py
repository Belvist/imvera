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
_IMPORTANT_TO_SHARE_QUESTION = (
    "Спасибо за разговор. Хотите ещё что-то добавить?"
)
# Phone-spoken brand. Latin «IMVERA» is skipped/garbled by Russian Silero TTS.
# Pronunciation: Амвера (not «им вера»).
_SERVICE_SPOKEN_NAME = "Амвера"


def service_spoken_name() -> str:
    return _SERVICE_SPOKEN_NAME


def summary_close_speech(
    state: EngineState,
    *,
    acknowledge: str = "",
) -> str:
    """Warm terminal close — never bare «Спасибо за разговор.»"""
    name = (state.elder_display_name or "").strip()
    if name:
        core = f"Всё, спасибо, {name}. Всего вам хорошего. До свидания."
    else:
        core = _SUMMARY_TEXT
    next_hint = (state.prior_call_context or {}).get("next_call_spoken", "").strip()
    if next_hint:
        if name:
            core = (
                f"Всё, спасибо, {name}. {next_hint} "
                "Всего вам хорошего. До свидания."
            )
        else:
            core = f"Всё, спасибо. {next_hint} Всего вам хорошего. До свидания."
    ack = acknowledge.strip()
    if ack:
        return f"{ack} {core}"
    return core


def goodbye_final_speech(state: EngineState) -> str:
    name = (state.elder_display_name or "").strip()
    if name:
        return f"До свидания, {name}. Всего вам хорошего."
    return _GOODBYE_FINAL


def important_to_share_question() -> str:
    return _IMPORTANT_TO_SHARE_QUESTION


def topic_question(intent: str) -> str:
    return _TOPIC_QUESTIONS.get(intent, "Расскажите, пожалуйста, чуть подробнее.")


def probe_question(phase: str, *, clarification: bool = False) -> str:
    key = f"probe_{phase}"
    if clarification:
        return _SLOT_CLARIFICATIONS.get(key, _PROBE_QUESTIONS.get(phase, "Повторите, пожалуйста."))
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


def wellness_ack(*, polarity: str | None = None, value: str = "") -> str:
    """Short ack after wellness slot fill — polarity-aware."""
    from packages.dialogue_engine.fast_interpreter import _detect_polarity, _normalize_core

    pol = polarity or _detect_polarity(value)
    core = _normalize_core(value)
    if pol == "negative":
        return _WELLNESS_ACK_NEGATIVE
    if pol == "uncertain" or re.match(
        r"^(так\s+себе|сойд[её]т|пойд[её]t|средн\w*|терпимо|ну\s+такое)\.?$", core, re.I
    ):
        return _WELLNESS_ACK_UNCERTAIN
    if re.match(r"^(пойд[её]т|терпимо|более-менее)\.?$", core, re.I):
        return _WELLNESS_ACK_OKAY
    normal_short = re.match(r"^(нормально|обычно|ничего|обычное)\.?$", core, re.I)
    if normal_short or "нормально" in value.lower():
        return _WELLNESS_ACK_NORMAL
    if pol == "positive":
        return _WELLNESS_ACK_GOOD
    return _WELLNESS_ACK


def opening_speech(elder_display_name: str, prior_context: dict[str, str] | None = None) -> str:
    from packages.dialogue_engine.check_path import prior_followup_question

    name = (elder_display_name or "").strip() or "вас"
    brand = _SERVICE_SPOKEN_NAME
    follow = prior_followup_question(prior_context or {})
    if follow:
        return f"Здравствуйте. Это сервис {brand}. {name}, {follow}"
    return (
        f"Здравствуйте. Это сервис {brand}. {name}, "
        f"{_SLOT_QUESTIONS['wellness']}"
    )


def slot_question(
    slot: str,
    *,
    clarification: bool = False,
    state: EngineState | None = None,
) -> str:
    if slot == "plans":
        if clarification:
            return _SLOT_CLARIFICATIONS["plans"]
        return plans_question(state)
    if clarification:
        return _SLOT_CLARIFICATIONS.get(slot, "Повторите, пожалуйста, коротко.")
    if slot.startswith("probe_"):
        return probe_question(slot.removeprefix("probe_"))
    if slot.startswith("episode_") or slot.startswith("topic_"):
        return "Расскажите, пожалуйста, чуть подробнее."
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
