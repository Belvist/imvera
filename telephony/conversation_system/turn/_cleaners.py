"""STT transcript cleaning — ported from core.dialogue.cleaners (logic only)."""
from __future__ import annotations

import re

_JUNK_RE = re.compile(
    r"^(\s*"
    r"(i|the|a|an|and|so|uh|um|huh|what|is it|are you|are you awake|do you)"
    r"[\s.,!?]*"
    r"|"
    r"(thank you|thanks|thanks for watching|thanks for listening|bye|bye-bye|"
    r"goodbye|good bye|hello|hi|next|you know|uh huh|mm hmm|hmm|okay|ok)"
    r"[\s.,!?]*"
    r"|"
    r"(спасибо|пока|пока-пока|всё|все|да|нет|ну|ага|угу|а|о|э|мм|хм|"
    r"привет|здравствуйте|до свидания)"
    r"[\s.,!?]*"
    r")$",
    re.IGNORECASE,
)

_SHORT_ANSWER_MAP = {
    "да": "да", "ага": "да", "угу": "да", "конечно": "да", "есть": "да",
    "окей": "да", "ок": "да", "давай": "да", "ус": "да", "ас": "да",
    "естественно": "да", "разумеется": "да", "точно": "да",
    "нет": "нет", "неа": "нет", "не нужно": "помощь не нужна",
    "не надо": "помощь не нужна", "нет спасибо": "помощь не нужна",
    "не хочу": "не хочу", "не стоит": "не стоит",
    "хорошо": "всё хорошо", "всё хорошо": "всё хорошо", "все хорошо": "всё хорошо",
    "нормально": "всё нормально", "норм": "всё нормально",
    "все нормально": "всё нормально", "всё нормально": "всё нормально",
    "неплохо": "всё нормально", "терпимо": "всё терпимо", "так себе": "так себе",
    "плохо": "всё плохо", "не важно": "неважно",
    "неважно": "неважно", "ничего": "ничего не нужно",
    "помощь": "нужна помощь", "помощь нужна": "нужна помощь",
    "помощь требуется": "нужна помощь", "нужна помощь": "нужна помощь",
    "помогите": "нужна помощь", "спасите": "нужна помощь",
    "больно": "мне больно", "болит": "что-то болит",
    "до свидания": "до свидания", "пока": "до свидания",
    "пока пока": "до свидания", "всего доброго": "до свидания",
    "спасибо": "спасибо", "большое спасибо": "спасибо",
    "благодарю": "спасибо", "спс": "спасибо",
    "здравствуйте": "здравствуйте", "привет": "привет",
    "алло": "алло", "ало": "алло", "алле": "алло", "ала": "алло",
    "здорово": "здорово", "отлично": "всё отлично",
    "супер": "всё отлично", "классно": "всё хорошо",
    "улучшилось": "всё хорошо", "снизилось": "всё хорошо",
    "стало легче": "всё хорошо", "перестало": "всё хорошо",
    "свело": "всё хорошо", "пошло": "всё хорошо",
}

_SHORT_ANSWER_WORDS = frozenset((
    "всё", "все", "да", "ага", "угу", "ок", "окей", "давай", "неплохо",
    "хорошо", "нормально", "норм", "терпимо", "неважно", "плохо",
    "помощь", "требуется", "нужна", "нужно", "надо", "не", "нуждаюсь",
    "нет", "нет спасибо", "не нужно", "не надо", "ничего", "спасибо",
    "есть", "конечно", "неа", "до", "свидания", "пока", "всего",
    "доброго", "большое", "здравствуйте", "привет", "алло", "ало", "алле", "ала", "ну",
    "ус", "ас", "естественно", "разумеется", "точно",
    "не хочу", "не стоит", "больно", "болит", "помогите", "спасите",
    "здорово", "отлично", "супер", "классно", "благодарю", "спс",
    "та", "даа", "дад", "ка", "дау", "дат", "таа", "неет", "нету",
    "ока", "ог", "уга", "гм", "мм", "хорош", "нормал", "помог",
    "приве", "драстующее", "зздравствуйте",
    "спасиб", "спасиба", "болшой", "окй", "оке",
    "улучшилось", "снизилось", "перестало", "свело", "пошло",
    "легче", "лучше", "помогло", "ушло", "исчез", "прошла", "ушёл",
    "стало", "куда-то", "наконец-то",
))

_HOMOPHONE = {
    "та": "да", "даа": "да", "дад": "да", "дадт": "да",
    "ка": "да", "дау": "да", "дат": "да", "таа": "да",
    "не": "нет", "нету": "нет", "неет": "нет", "неаа": "нет",
    "ока": "ага", "ог": "угу", "агаа": "ага", "уга": "угу",
    "угуу": "угу", "гм": "угу", "мм": "ага",
    "хорош": "хорошо", "хорошо": "хорошо",
    "нормал": "нормально", "нормально": "нормально",
    "помощ": "помощь", "помог": "помощь",
    "приве": "привет", "драстуйте": "здравствуйте",
    "ало": "алло", "ала": "алло", "алле": "алло", "привет": "привет",
    "драстуйте": "здравствуйте", "драствуйте": "здравствуйте",
    "дравствуйте": "здравствуйте", "зравствуйте": "здравствуйте",
    "спасиб": "спасибо", "спасиба": "спасибо", "болшой": "большое",
    "спокойной": "до свидания", "всегдоброго": "всего доброго",
    "ок": "ок", "окй": "окей", "оке": "окей",
    "пжалста": "пожалуйста",
}


def _is_repetition(text: str) -> bool:
    words = re.findall(r"[а-яёa-z]+", text.lower())
    if len(words) < 3:
        return False
    return len(set(words)) == 1 and len(words) >= 3


_PHONE_SOCIAL_CANONICAL = frozenset({
    "алло", "здравствуйте", "привет", "спасибо", "до свидания",
})

_WELLNESS_SHORT_CANONICAL = frozenset({
    "всё хорошо", "всё нормально", "всё плохо", "всё терпимо", "всё отлично",
    "так себе", "неважно", "ничего не нужно",
    "нужна помощь", "помощь не нужна", "не хочу", "не стоит",
    "мне больно", "что-то болит", "здорово",
})


def is_phone_social_short(raw: str | None) -> bool:
    """Phone check-in or social pleasantry — not wellness content."""
    canon = short_real_answer(raw)
    return bool(canon and canon in _PHONE_SOCIAL_CANONICAL)


def wellness_short_answer(raw: str | None) -> str | None:
    """Short answer that actually addresses wellness / yes-no control."""
    canon = short_real_answer(raw)
    if not canon or canon in _PHONE_SOCIAL_CANONICAL:
        return None
    if canon in _WELLNESS_SHORT_CANONICAL:
        return canon
    return None


def short_real_answer(raw: str | None) -> str | None:
    """Canonical form of a short real answer, or None."""
    if not raw:
        return None
    t = raw.strip().lower()
    t = re.sub(r"[.,!?…:;]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return None
    words = t.split()
    if len(words) > 3:
        return None
    rewritten = [_HOMOPHONE.get(w, w) for w in words]
    canon_t = " ".join(rewritten)
    direct = _SHORT_ANSWER_MAP.get(t) or _SHORT_ANSWER_MAP.get(canon_t)
    if direct:
        return direct
    allowed = _SHORT_ANSWER_WORDS
    if not all((w in allowed or _HOMOPHONE.get(w) in allowed) for w in words):
        return None
    return _SHORT_ANSWER_MAP.get(canon_t) or _SHORT_ANSWER_MAP.get(t)


def clean_transcript(text: str | None) -> str | None:
    """Strip junk/hallucinations; recover short real answers."""
    if not text:
        return None
    t = text.strip()
    if len(t) < 2:
        return None
    if _JUNK_RE.match(t):
        short = short_real_answer(t)
        if short:
            return short
        return None
    if _is_repetition(t):
        return None
    words = re.findall(r"[а-яёa-z0-9]+", t.lower())
    if 1 <= len(words) <= 3:
        short = short_real_answer(t)
        if short:
            return short
    return t
