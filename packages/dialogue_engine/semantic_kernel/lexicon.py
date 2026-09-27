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
        # Kin gaps (false-world third-party illness must not be ISSUE_SITE)
        "внук",
        "внучка",
        "внуки",
        "племянник",
        "племянница",
        "зять",
        "невестка",
        "тесть",
        "теща",
        "тёща",
        "свекор",
        "свекровь",
        "дядя",
        "тетя",
        "тётя",
        "кум",
        "кума",
        "родственник",
        "родственница",
    }
)

SPEAKER_MARKERS: frozenset[str] = frozenset({"я", "меня", "мне", "мной", "мною"})

# Inflection-proof kin stems: Russian cases (племянницы, зятя, внуку) must
# match like nominatives. Left-anchored so «замуж»/«регулярно» never hit.
OTHER_PERSON_RES: tuple[str, ...] = (
    # Explicit alternations (bare stems hit «другая нога»/«мужчина»/«папка»/«тест»).
    r"\bсосед\w*", r"\bсоседк\w*",
    r"\bвнук\w*", r"\bвнуч\w*",
    r"\bдоч(?:ь|ери|ерью|ка|ки|ке|ку|кой|ек|урка)?\b",
    r"\bсын\w*", r"\bсынов\w*",
    r"\bмам\w*", r"\bматер\w*",
    r"\bпап(?:а|у|ой|е|ы|ин)?\b",
    r"\bот[еэ]ц\w*",
    r"\bбрат\w*", r"\bбрать\w*",
    r"\bсестр\w*",
    r"\bродственни\w*",
    r"\bмуж(?:а|у|ем|е)?\b",
    r"\bжен(?:а|ы|у|ой|е)?\b", r"\bженщин\w*",
    r"\bсупруг\w*",
    r"\bзят(?:ь|я|ю|ем|е|ья|ьям|ьями)?\b",
    r"\bневест\w*",
    r"\bтесть\b|\bтестя\b|\bтестем\b",
    r"\bтещ\w*",
    r"\bсвекр\w*", r"\bсвекров\w*",
    r"\bдяд\w*", r"\bтет\w*",
    r"\bплемянни\w*",
    r"\bкум\w*",
    r"\bдевер\w*", r"\bшурин\w*", r"\bзолов\w*", r"\bсвояк\w*",
    r"\bбабуш\w*", r"\bдедуш\w*",
    r"\bврач\w*", r"\bдоктор\w*", r"\bмедсестр\w*",
    r"\bдруг(?:а|у|ом|е)?\b", r"\bдруз\w+", r"\bподруг\w*",
)

_OTHER_PERSON_RE = None


def has_other_person(text: str) -> bool:
    """Inflection-proof third-party detection (all cases/numbers)."""
    global _OTHER_PERSON_RE
    import re

    if _OTHER_PERSON_RE is None:
        _OTHER_PERSON_RE = re.compile("|".join(OTHER_PERSON_RES), re.I)
    low = (text or "").lower().replace("ё", "е")
    return bool(_OTHER_PERSON_RE.search(low))


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

# Level-0 controls: see semantic_kernel/controls.py (canonical contract).
