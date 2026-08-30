"""Vocabulary-based plausibility gate for the STT transcript (FIXES_PLAN P1b).

whisper-tiny on real phone audio sometimes emits CONFIDENT-LOOKING nonsense
that sails over the 0.55 confidence gate ("Торатичина" conf 0.614, "Лоха!"
0.763) and then pollutes the dialogue: Vera echoes it, the agenda re-asks the
same question. Pure confidence cannot separate "уверенная бессмыслица" from
real speech — a vocabulary gate can.

Contract:
  * ``contains_real_word(text)`` — True when at least one token (after a
    light Russian suffix-strip) matches the product/health lexicon, or when
    the transcript carries a critical health entity (fall, pain, meds,
    doctor, pressure, heart...). Those are NEVER gated: losing "упал" is
    worse than a false positive.
  * ``looks_like_garbage(text)`` — ``not contains_real_word(text)``.

The lexicon is intentionally small and product-scoped (this is a care-call
domain, not general Russian); a transcript of real Russian normally carries
at least one word from it. Noise like "Торатичина" / "Лоха" / "палговору"
carries none.
"""

import re

# Roots that must ALWAYS survive the gate: health/safety-critical content.
# "у палок не ударилось" (a real fall miscue) keeps its ход because «удар»
# is critical; gating it away would silently lose a fall.
CRITICAL_HEALTH_ROOTS = frozenset((
    "упа", "пада", "удар", "болит", "бол", "голов", "табл", "лекар",
    "врач", "доктор", "давл", "сердц", "температур", "приступ", "скор",
    "неотлож", "помог", "помощ", "плох", "боль", "кров", "сознани",
    "тошн", "круж", "слаб", "худ", "нездоров",
))

# Product/domain lexicon (core roots). Small by design — see module docstring.
# Includes daily-life words the agenda actually asks about (sleep, mood,
# plans, family) and the common short answers ("да", "хорошо", "слышно"...).
CORE_ROOTS = frozenset((
    # affirmations / short answers
    "да", "нет", "ага", "угу", "ладно", "хорошо", "нормальн", "отлич",
    "прекрасн", "замечательн", "порядк", "спасиб", "пожалуйст", "слыш",
    "понят", "верно", "точно", "конечно", "знаю", "не знаю",
    # wellbeing / feelings
    "самочувств", "чувств", "настроени", "спокойн", "бодр", "здоров",
    "уста", "отдых", "отдох", "хоч", "хочу", "сон", "спал", "спала",
    "спать", "выспа", "бессонн", "ночь", "утро", "вечер", "день",
    # body / health daily
    "рука", "нога", "спина", "живот", "шея", "плеч", "колен", "сустав",
    "ухо", "нос", "горл", "зуб", "зрени", "слух", "давл", "пульс",
    "температур", "принима", "выпил", "выпила", "пью", "лекарств",
    "пил", "пить", "попи", "ча", "чай",
    # plans / activities
    "план", "делать", "займ", "гуля", "погул", "прогул", "чита", "книг",
    "смотр", "телевизор", "сериал", "готов", "кухн", "еда", "суп", "ча",
    "магазин", "продукт", "аптек", "уборк", "стирк", "вяза", "сад",
    "огород", "церков", "гост", "приезжа", "встреч", "вар", "печь",
    # family / people
    "родн", "близк", "семь", "сын", "дочь", "дочер", "внук", "внучк",
    "бабушк", "дедушк", "мам", "пап", "брат", "сестр", "сосед", "подруг",
    "муж", "жен", "друг",
    # home / weather / small talk
    "дом", "дома", "квартир", "комнат", "окно", "погод", "дожд", "снег",
    "солнц", "тепл", "холод", "ветер", "улиц", "палк",
    # dialogue mechanics
    "повтори", "ещё", "снова", "медленн", "громче", "алло", "здравств",
    "привет", "добрый", "свидани", "пока", "всё", "все", "добав",
    "передать", "записать", "записа", "увидит", "важно", "ничего", "что",
    # verbs / small talk glue
    "говор", "сказ", "расскаж", "дела", "была", "был", "были", "буд",
    "есть", "быть", "сидел", "сидела", "ходил", "ходила", "пошл",
    "пришл", "ушел", "ушла", "вернул", "ждал", "ждала",
))

# Function words / pronouns: their presence is itself a strong signal of
# real speech (whisper noise almost never emits "мне"+"сейчас" coherently).
FUNCTION_WORDS = frozenset((
    "я", "ты", "мы", "вы", "он", "она", "они", "мне", "меня", "тебя",
    "нас", "вас", "ему", "ей", "их", "его", "себя", "мой", "моя", "мои",
    "твой", "наш", "ваш", "это", "этот", "эта", "эти", "так", "как",
    "где", "когда", "почему", "зачем", "что", "кто", "очень", "тоже",
    "сейчас", "потом", "сегодня", "вчера", "завтра", "там", "тут",
    "здесь", "ну", "и", "а", "но", "или", "же", "бы", "ли", "не", "но",
    "да", "во", "за", "на", "по", "со", "от", "до", "из", "у", "о",
))

# Light Russian suffix set for the core-stem match (longest-first).
_SUFFIXES = (
    "ами", "ями", "ах", "ях", "ой", "ей", "ую", "юю", "ий", "ый",
    "ое", "ее", "ая", "яя", "ешь", "ишь", "ем", "им", "ом", "ать",
    "ять", "ет", "ит", "ут", "ют", "ат", "ил", "ла", "ло", "ли",
    "ал", "ы", "и", "а", "я", "о", "е", "у", "ю", "ь",
)

# Tokens observed verbatim in real calls that are pure ASR noise. Kept small
# and exact (never root-based) so real speech is never collateral.
OBSERVED_NOISE = frozenset((
    "торатичина", "лоха", "палговор", "палговору", "осуши", "суши",
    "восподн", "оттвыж", "восподнанговарив",
))


def _tokens(text):
    """Lower-cased Cyrillic/alnum tokens (len >= 2)."""
    if not text:
        return []
    out, cur = [], []
    for ch in text.lower():
        if ch.isalpha() or ch.isdigit():
            cur.append(ch)
        else:
            if cur:
                out.append("".join(cur))
                cur = []
    if cur:
        out.append("".join(cur))
    return [t for t in out if len(t) >= 2]


def _stem(tok):
    """Yield tok and its suffix-stripped forms (longest suffix first)."""
    yield tok
    for suf in _SUFFIXES:
        if len(tok) > len(suf) + 2 and tok.endswith(suf):
            yield tok[:-len(suf)]


def _core_hit(tok):
    """True when tok or a stem is in the core lexicon. Longer core roots
    (> 4 chars) also match as prefixes so inflected forms ("здравствуйте",
    "хорошая") are not lost to a short suffix-strip."""
    for stem in _stem(tok):
        if stem in CORE_ROOTS:
            return True
        if len(stem) >= 5:
            for root in CORE_ROOTS:
                if len(root) >= 5 and stem.startswith(root):
                    return True
    return False


def contains_real_word(text):
    """True when the transcript carries a real domain/health word or a
    critical health entity. Pure noise → False."""
    toks = _tokens(text)
    if not toks:
        return False
    for tok in toks:
        if tok in OBSERVED_NOISE:
            continue
        if any(tok.startswith(r) for r in CRITICAL_HEALTH_ROOTS):
            return True
        if tok in FUNCTION_WORDS:
            return True
        if _core_hit(tok):
            return True
    # 3+ distinct words that are not observed noise: whisper-tiny never emits
    # a three-word run of pure noise; treat it as speech rather than risk
    # gating a real utterance (false-positive cost is a lost turn).
    meaningful = [t for t in toks if t not in OBSERVED_NOISE]
    return len(meaningful) >= 3


def looks_like_garbage(text):
    """whisper garbage (confident nonsense) has no real word in it."""
    if not text or not text.strip():
        return False  # empty is handled elsewhere (silence/echo path)
    return not contains_real_word(text)


def repair_fall_miscue(text):
    """Restore fall hints when STT mangles «упал» into «у палок не ударилось».

    Real call ca81bc3ac2c7: vocab kept «удар» but SafetyEngine needs «упал».
    """
    if not text:
        return text
    low = text.lower()
    if re.search(r"упа|пада", low):
        return text
    if re.search(r"пал\w*", low) and re.search(r"удар", low):
        return text + " упал"
    return text