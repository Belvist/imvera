"""Russian surface meanings for renderer — no internal English enums in prompts."""
from __future__ import annotations

from golden_path.slots import SlotName

QUESTION_MEANING_RU: dict[str, str] = {
    "wellness_now": "как человек себя чувствует сейчас",
    "mood_today": "какое настроение сегодня",
    "sleep_last_night": "как прошла ночь / как человек спал",
    "plans_today": "планы на сегодня",
}

FORBIDDEN_TOPIC_RU: dict[str, str] = {
    "wellness": "самочувствие",
    "mood": "настроение",
    "sleep": "сон",
    "plans": "планы",
}

SYMPTOM_PREP_RU: dict[str, str] = {
    "head": "голове",
    "back": "спине",
    "knee": "колене",
    "leg": "ноге",
    "arm": "руке",
    "abdomen": "животе",
    "heart": "сердце",
    "pressure": "давлении",
    "throat": "горле",
    "chest": "груди",
}

SLOT_QUESTION_EXAMPLE: dict[SlotName, str] = {
    SlotName.WELLNESS: "Как вы сейчас себя чувствуете?",
    SlotName.MOOD: "Какое у вас сегодня настроение?",
    SlotName.SLEEP: "Как вы спали этой ночью?",
    SlotName.PLANS: "Что планируете на сегодня?",
}


def symptom_prep_phrase(code: str) -> str | None:
    return SYMPTOM_PREP_RU.get(code)


def format_facts_ru(facts: dict[str, str]) -> list[str]:
    """Human-readable fact lines for renderer — no raw enum keys."""
    lines: list[str] = []
    for key, value in facts.items():
        if key == "symptom":
            prep = symptom_prep_phrase(str(value))
            if prep:
                lines.append(f"уточнённый симптом: {prep}")
            continue
        if key == "answered_slot":
            topic = FORBIDDEN_TOPIC_RU.get(str(value), str(value))
            lines.append(f"тема «{topic}» уже обсуждена")
            continue
        if key in ("refused_slot",):
            topic = FORBIDDEN_TOPIC_RU.get(str(value), str(value))
            lines.append(f"пользователь отказался от темы «{topic}»")
            continue
        if key in ("user_fatigue", "wait_request", "improvement"):
            continue
        if "=" in str(value):
            continue
        lines.append(f"{key}: {value}")
    return lines
