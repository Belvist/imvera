"""Data-driven anatomical / issue lexicons — not per-symptom conversation branches."""

from __future__ import annotations

# Normalized lemmas — morphology layer maps inflected forms here.
BODY_SITE_LEMMAS: frozenset[str] = frozenset(
    {
        "голова",
        "шея",
        "горло",
        "грудь",
        "грудная",
        "клетка",
        "живот",
        "спина",
        "поясница",
        "колено",
        "локоть",
        "плечо",
        "запястье",
        "лодыжка",
        "стопа",
        "палец",
        "рука",
        "нога",
        "ухо",
        "глаз",
        "зуб",
        "сердце",
        "сустав",
        "таз",
        "бедро",
        "кисть",
        "челюсть",
        "висок",
        "лоб",
        "нос",
        "печень",
        "почка",
    }
)

ISSUE_VERB_LEMMAS: frozenset[str] = frozenset(
    {
        "болеть",
        "ныть",
        "ломить",
        "тянуть",
        "давить",
        "першить",
        "заложить",
        "онеметь",
        "кружиться",
        "тошнить",
        "кашлять",
        "чихать",
        "слабеть",
        "уставать",
        "беспокоить",
        "мешать",
        "затруднять",
    }
)

OTHER_PERSON_MARKERS: frozenset[str] = frozenset(
    {
        "муж",
        "жена",
        "мама",
        "мать",
        "папа",
        "отец",
        "сын",
        "дочь",
        "бабушка",
        "дедушка",
        "сосед",
        "соседка",
        "врач",
        "медсестра",
        "друг",
        "подруга",
        "брат",
        "сестра",
    }
)

SPEAKER_MARKERS: frozenset[str] = frozenset({"я", "меня", "мне", "мной", "мною"})

REFERENCE_MARKERS: frozenset[str] = frozenset(
    {
        "это",
        "оно",
        "там",
        "тоже",
        "ещё",
        "еще",
        "всё",
        "все",
        "про",
    }
)

CONTROL_EXACT: dict[str, str] = {
    "да": "yes",
    "нет": "no",
    "угу": "backchannel",
    "ага": "backchannel",
    "повторите": "repeat",
    "повтори": "repeat",
    "алло": "repeat",
    "стоп": "stop",
    "хватит": "stop",
    "позже": "defer",
    "не знаю": "unknown",
    "не помню": "unknown",
    "не хочу": "refuse",
    "не хочу разговаривать": "refuse",
}
