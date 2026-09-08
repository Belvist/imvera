"""Question copy for pilot daily-check slots."""

from __future__ import annotations

_SLOT_QUESTIONS: dict[str, str] = {
    "wellness": "Как вы себя чувствуете?",
    "mood": "А какое у вас сегодня настроение?",
    "sleep": "Как вы спали?",
    "plans": "Какие у вас планы на сегодня?",
}

_SLOT_CLARIFICATIONS: dict[str, str] = {
    "wellness": "Расскажите, пожалуйста, о самочувствии хотя бы в двух словах.",
    "mood": "Как у вас настроение — хотя бы коротко?",
    "sleep": "Как вы спали — коротко, пожалуйста?",
    "plans": "Какие у вас планы на сегодня — в двух словах?",
}

_REPAIR_ACK = "Да, слышу."
_PARTIAL_CLOSE = "Сейчас не получилось узнать, как у вас дела. До свидания."
_GOODBYE_CONFIRM = "Вы хотите закончить разговор?"
_GOODBYE_FINAL = "До свидания. Хорошего дня."
_GOODBYE_MARKERS = ("до свидания", "всего доброго")
_WELLNESS_ACK = "Хорошо."
_WELLNESS_ACK_GOOD = "Рада это слышать."
_WELLNESS_ACK_NORMAL = "Понятно."
_WELLNESS_ACK_OKAY = "Хорошо, поняла."
_WELLNESS_ACK_UNCERTAIN = "Понимаю."
_WELLNESS_ACK_NEGATIVE = "Мне жаль это слышать."
_SUMMARY_TEXT = "Спасибо за разговор."
_ANSWER_WAIT_MS = 7000


def wellness_ack(*, polarity: str | None = None, value: str = "") -> str:
    """Short ack after wellness slot fill — polarity-aware."""
    from packages.dialogue_engine.fast_interpreter import _detect_polarity, _normalize_core
    import re

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
    if re.match(r"^(нормально|обычно|ничего|обычное)\.?$", core, re.I) or "нормально" in value.lower():
        return _WELLNESS_ACK_NORMAL
    if pol == "positive":
        return _WELLNESS_ACK_GOOD
    return _WELLNESS_ACK


def opening_speech(elder_display_name: str) -> str:
    return (
        f"Здравствуйте. Это сервис IMVERA, {elder_display_name}. "
        f"{_SLOT_QUESTIONS['wellness']}"
    )


def slot_question(slot: str, *, clarification: bool = False) -> str:
    if clarification:
        return _SLOT_CLARIFICATIONS.get(slot, "Повторите, пожалуйста, коротко.")
    return _SLOT_QUESTIONS[slot]


def repair_response(delivered_text: str) -> str:
    return f"{_REPAIR_ACK} {_repeat_question(delivered_text)}"


def _repeat_question(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "Повторите, пожалуйста."
    if stripped.endswith("?"):
        return stripped
    return f"Я спросила: {stripped}"
