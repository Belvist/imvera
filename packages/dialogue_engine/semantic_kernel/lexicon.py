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
        # Elder-speech sites (battery 2026-09-30; collision-checked: рот
        # is 3 letters so the 4-letter fuzzy matcher skips it as a source;
        # лицо only matches лицо-forms within length 2).
        "рот",
        "лицо",
        "печень",
        "почка",
        # Extended sites (hard1000 coverage; each verified against the
        # 4-letter fuzzy matcher for collisions before merge).
        "затылок",
        "макушка",
        "подбородок",
        "щека",
        "скула",
        "губа",
        "язык",
        "десна",
        "гортань",
        "ключица",
        "лопатка",
        "ребро",
        "грудина",
        "подмышка",
        "крестец",
        "копчик",
        "пах",
        "икра",
        "пятка",
        "щиколотка",
        "предплечье",
        "голень",
        "ступня",
        "бок",
        "подреберье",
        "желудок",
        "кишечник",
        "легкое",
        "селезенка",
        "бронхи",
        "трахея",
        "пищевод",
        "веко",
        "бровь",
        "переносица",
        "ноздря",
        "сустав",
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
        "дрожать",
        # Elder-speech verbs (battery 2026-09-30) — mirrors the mention
        # layer's generic verb list so kernel spans agree.
        "щемить",
        "гудеть",
        "звенеть",
        "слезиться",
        "чесаться",
        "гореть",
        "сохнуть",
        "хрустеть",
        "скрючивать",
        "сводить",
        "колотить",
        "рвать",
        "хрипеть",
        "драть",
        "шатать",
        "подкашивать",
        "неметь",
        "отекать",
        "пухнуть",
        "темнеть",
        "потеть",
        "задыхаться",
        "слабить",
        "закрепить",
        "частить",
        "замирать",
        "скакать",
        "заклинить",
        "отниматься",
        "хворать",
        "лихорадить",
    }
)

# Sensation nouns — complaints without a pain verb («тяжесть в животе»,
# «жжение в груди»). Normalized lemmas; span_parser pairs them with a body
# site in the same clause. Deliberately excludes hunger/thirst/appetite
# words (see _FALSE_SENSATION_TOKENS in span_parser).
SENSATION_NOUNS: frozenset[str] = frozenset(
    {
        "тяжесть",
        "жжение",
        "резь",
        "ломота",
        "колика",
        "колики",
        "спазм",
        "спазмы",
        "судорога",
        "судороги",
        "онемение",
        "покалывание",
        "зуд",
        "дрожь",
        "озноб",
        "потливость",
        "слабость",
        "усталость",
        "одышка",
        "удушье",
        "сердцебиение",
        "отек",
        "синяк",
        "сыпь",
        "головокружение",
        "тошнота",
        "рвота",
        "кашель",
        "насморк",
        "чихание",
        "икота",
        "отрыжка",
        "изжога",
        "запор",
        "понос",
        "кровь",
        "гной",
        "шум",
        "звон",
        "туман",
        "двоение",
        "сухость",
        "мокрота",
        "лихорадка",
        "першение",
        "горечь",
        "жажда",
        "боль",
        "боли",
    }
)

# Severity adverbs — how much it hurts. Matched as whole words only;
# never a symptom by themselves.
SEVERITY_WORDS: frozenset[str] = frozenset(
    {
        "чуть",
        "слегка",
        "немного",
        "средне",
        "сильно",
        "очень",
        "порядком",
        "жутко",
        "дико",
        "невыносимо",
        "нестерпимо",
        "ужасно",
        "страшно",
        "кошмарно",
        "едва",
        "терпимо",
        "еле",
    }
)

# Time anchors for onset/duration («со вчера» stays the onset anchor).
TIME_WORDS: frozenset[str] = frozenset(
    {
        "днем",
        "утром",
        "вечером",
        "ночью",
        "после обеда",
        "перед сном",
        "среди ночи",
        "под утро",
        "в обед",
        "к вечеру",
        "неделю назад",
        "месяц назад",
        "с понедельника",
        "на днях",
        "недавно",
        "изредка",
        "часто",
        "каждый день",
        "по утрам",
        "по вечерам",
        "по ночам",
        "весь день",
        "всю ночь",
        "второй день",
        "третий день",
        "неделю",
        "месяц",
    }
)

# Medication vocabulary for the meds slot (coverage.py markers).
MEDICATION_WORDS: frozenset[str] = frozenset(
    {
        "таблетка",
        "пилюля",
        "лекарство",
        "препарат",
        "медикамент",
        "витамины",
        "витамин",
        "капли",
        "мазь",
        "укол",
        "инсулин",
        "антибиотик",
        "сироп",
        "порошок",
        "спрей",
        "ингалятор",
        "пластырь",
        "микстура",
        "настойка",
        "отвар",
    }
)

# Food vocabulary for the nutrition slot.
FOOD_WORDS: frozenset[str] = frozenset(
    {
        "завтрак",
        "обед",
        "ужин",
        "полдник",
        "суп",
        "каша",
        "хлеб",
        "булка",
        "чай",
        "кофе",
        "молоко",
        "кефир",
        "яблоко",
        "банан",
        "апельсин",
        "картошка",
        "картофель",
        "макароны",
        "рис",
        "гречка",
        "мясо",
        "рыба",
        "курица",
        "яйцо",
        "сыр",
        "творог",
        "сметана",
        "масло",
        "сахар",
        "соль",
        "вода",
        "сок",
        "компот",
        "кисель",
        "пирог",
        "пирожок",
        "печенье",
        "конфета",
        "мед",
        "варенье",
        "салат",
        "овощи",
        "фрукты",
        "котлета",
        "сосиска",
        "колбаса",
        "пельмени",
        "борщ",
        "щи",
        "уха",
        "окрошка",
        "блины",
        "оладьи",
        "яичница",
        "омлет",
        "бутерброд",
    }
)

# Sleep vocabulary for the sleep slot.
SLEEP_WORDS: frozenset[str] = frozenset(
    {
        "бессонница",
        "дремала",
        "дремал",
        "ворочался",
        "ворочалась",
        "просыпался",
        "просыпалась",
        "кошмар",
        "кошмары",
        "храп",
        "снотворное",
        "сон",
        "спал",
        "спала",
        "выспался",
        "выспалась",
    }
)

# Mood vocabulary. Negative set is deliberately soft words only — hard
# negatives («плохо», «ужасно») already belong to wellness/safety paths.
MOOD_WORDS_NEG: frozenset[str] = frozenset(
    {
        "грустно",
        "тоскливо",
        "одиноко",
        "тревожно",
        "скучно",
        "обидно",
        "досадно",
        "уныло",
        "печально",
        "расстроен",
        "расстроена",
        "переживаю",
        "волнуюсь",
        "боюсь",
        "нервничаю",
    }
)

MOOD_WORDS_POS: frozenset[str] = frozenset(
    {
        "весело",
        "бодро",
        "отлично",
        "прекрасно",
        "замечательно",
        "спокойно",
        "радостно",
        "доволен",
        "довольна",
        "счастлив",
        "счастлива",
    }
)

# Background-noise vocabulary — TV/music chatter that must never become a
# complaint or a slot answer (side-chatter false world).
NOISE_WORDS: frozenset[str] = frozenset(
    {
        "телевизор",
        "телик",
        "сериал",
        "передача",
        "новости",
        "музыка",
        "радио",
        "песня",
        "кино",
        "фильм",
        "футбол",
        "хоккей",
        "концерт",
        "реклама",
        "шоу",
        "программа",
        "мультик",
    }
)

OTHER_PERSON_MARKERS: frozenset[str] = frozenset(    {
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
