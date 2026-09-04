"""Token-level semantic matching for slot and symptom detection.

Priority (highest first):
1. Explicit topic lexical evidence (whole-token / bounded stems)
2. Pending-slot contextual answer (short generic polarity)
3. Generic polarity alone never picks a global slot without pending context.

No raw substring scans across unrelated tokens (e.g. «доч» inside «секундочку»).
"""
from __future__ import annotations

import re
from typing import Iterable

from golden_path.slots import SlotName, SLOT_ORDER

_TOKEN_RE = re.compile(r"[а-яё]+", re.IGNORECASE)

# Minimum stem length for prefix match on a single token (avoids «ног» in «особенного»).
_MIN_STEM_LEN = 4

# Whole-token or prefix stems — matched only against tokenized words.
MOOD_TOKEN_STEMS: tuple[str, ...] = (
    "настроение",
    "настроении",
    "настроения",
    "настроен",
    "настроена",
    "настроены",
)

SLEEP_TOKEN_STEMS: tuple[str, ...] = (
    "спал",
    "спала",
    "спали",
    "сплю",
    "спим",
    "спать",
    "сон",
    "сне",
    "сном",
    "ночь",
    "ночью",
    "проснулся",
    "проснулась",
    "проснулись",
    "бессонница",
    "бессонницу",
    "дремал",
    "дремала",
    "засыпал",
    "засыпала",
)

PLANS_ACTION_STEMS: tuple[str, ...] = (
    "планирую",
    "планируем",
    "планирует",
    "план",
    "планы",
    "собираюсь",
    "собираемся",
    "пойду",
    "поеду",
    "встреча",
    "встречу",
    "прогулка",
    "прогулку",
    "магазин",
)

# Family/visit nouns answer «plans» only in short replies or when plans is pending.
PLANS_FAMILY_STEMS: tuple[str, ...] = (
    "внуки",
    "внучка",
    "внучки",
    "дочь",
    "дочери",
    "сын",
    "сына",
    "родственники",
    "гости",
    "гостей",
)

PLANS_PHRASE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bничего\s+особенн\w*\b",
        r"\bне\s+планиру\w*\b",
        r"\bдома\s+посиж\w*\b",
    )
)

WELLNESS_SYMPTOM_STEMS: tuple[str, ...] = (
    "голова",
    "голову",
    "голове",
    "головой",
    "спина",
    "спине",
    "спину",
    "живот",
    "животе",
    "нога",
    "ноге",
    "ноги",
    "ногу",
    "колено",
    "колене",
    "колену",
    "рука",
    "руке",
    "руку",
    "сердце",
    "сердца",
    "давление",
    "давлении",
    "горло",
    "горле",
    "грудь",
    "груди",
    "температура",
    "температурой",
    "болит",
    "больно",
    "болела",
    "болел",
    "кашель",
    "кашля",
    "простуда",
    "простуде",
    "таблетка",
    "таблетки",
    "лекарство",
    "лекарства",
    "недомогание",
    "симптом",
    "симптомы",
)

WELLNESS_TOPIC_STEMS: tuple[str, ...] = (
    "самочувствие",
    "самочувствии",
    "здоровье",
    "здоровьем",
)

# Generic polarity — never assigns a slot without pending context.
GENERIC_POLARITY_TOKENS: frozenset[str] = frozenset(
    {
        "нормально",
        "норм",
        "хорошо",
        "плохо",
        "да",
        "нет",
        "ага",
        "угу",
        "ладно",
        "ок",
        "окей",
        "так",
        "вроде",
        "пойдет",
        "пойдёт",
        "сойдет",
        "сойдёт",
    }
)

SYMPTOM_CODE_BY_STEM: dict[str, str] = {
    "голова": "head",
    "голову": "head",
    "голове": "head",
    "головой": "head",
    "голов": "head",
    "спина": "back",
    "спине": "back",
    "спину": "back",
    "спин": "back",
    "живот": "abdomen",
    "животе": "abdomen",
    "нога": "leg",
    "ноге": "leg",
    "ноги": "leg",
    "ногу": "leg",
    "колено": "knee",
    "колене": "knee",
    "колену": "knee",
    "колен": "knee",
    "рука": "arm",
    "руке": "arm",
    "руку": "arm",
    "рук": "arm",
    "сердце": "heart",
    "сердца": "heart",
    "сердц": "heart",
    "давление": "pressure",
    "давлении": "pressure",
    "давлен": "pressure",
    "горло": "throat",
    "горле": "throat",
    "горл": "throat",
    "грудь": "chest",
    "груди": "chest",
    "груд": "chest",
}

WAIT_REQUEST_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bсекундочк\w*\b",
        r"\bминуточк\w*\b",
        r"\bподожд\w*\b",
        r"\bпогод(?:и|ите)\w*\b",
        r"\bсейчас\s+вспомн\w*\b",
        r"\bдайте\s+подумать\b",
        r"\bмомент\w*\b",
    )
)

USER_FATIGUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bустал\w*\s+.*\bотвеч\w*\b",
        r"\bустала\w*\s+.*\bотвеч\w*\b",
        r"\bнадоел\w*\s+.*\bотвеч\w*\b",
        r"\bхватит\s+.*\bвопрос\w*\b",
        r"\bустал\s+уже\b",
        r"\bустала\s+уже\b",
    )
)

_LONG_NARRATIVE_TOKEN_THRESHOLD = 8


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _stem_matches_token(token: str, stem: str) -> bool:
    if not token or not stem:
        return False
    if token == stem:
        return True
    if len(stem) < _MIN_STEM_LEN:
        return token == stem
    return token.startswith(stem) and len(token) <= len(stem) + 5


def _any_token_matches_stems(tokens: Iterable[str], stems: tuple[str, ...]) -> bool:
    for token in tokens:
        for stem in stems:
            if _stem_matches_token(token, stem):
                return True
    return False


def _matches_phrase_patterns(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(p.search(text) for p in patterns)


def is_wait_request(text: str) -> bool:
    return _matches_phrase_patterns(text, WAIT_REQUEST_PATTERNS)


def is_user_fatigue(text: str) -> bool:
    return _matches_phrase_patterns(text, USER_FATIGUE_PATTERNS)


def is_generic_polarity_answer(tokens: list[str]) -> bool:
    if not tokens:
        return False
    meaningful = [t for t in tokens if t not in {"я", "в", "и", "а", "ну", "вроде", "как", "то"}]
    if not meaningful:
        return False
    return all(t in GENERIC_POLARITY_TOKENS for t in meaningful)


def _explicit_slot_scores(tokens: list[str], text: str) -> dict[SlotName, int]:
    scores: dict[SlotName, int] = {slot: 0 for slot in SLOT_ORDER}

    if _any_token_matches_stems(tokens, MOOD_TOKEN_STEMS):
        scores[SlotName.MOOD] += 10

    if _any_token_matches_stems(tokens, SLEEP_TOKEN_STEMS):
        scores[SlotName.SLEEP] += 10

    plans_phrase = _matches_phrase_patterns(text, PLANS_PHRASE_PATTERNS)
    plans_action = _any_token_matches_stems(tokens, PLANS_ACTION_STEMS)
    if plans_phrase or plans_action:
        scores[SlotName.PLANS] += 10 if plans_phrase else 8
    elif _any_token_matches_stems(tokens, PLANS_FAMILY_STEMS):
        # Narrative family mention is not a plans-slot answer by itself.
        if len(tokens) < _LONG_NARRATIVE_TOKEN_THRESHOLD:
            scores[SlotName.PLANS] += 8

    wellness_symptom = _any_token_matches_stems(tokens, WELLNESS_SYMPTOM_STEMS)
    wellness_topic = _any_token_matches_stems(tokens, WELLNESS_TOPIC_STEMS)
    if wellness_symptom:
        scores[SlotName.WELLNESS] += 7
    if wellness_topic:
        scores[SlotName.WELLNESS] += 9

    return scores


def _pick_highest_explicit_slot(scores: dict[SlotName, int]) -> SlotName | None:
    best: SlotName | None = None
    best_score = 0
    for slot in SLOT_ORDER:
        score = scores[slot]
        if score > best_score:
            best_score = score
            best = slot
    return best if best_score > 0 else None


def detect_slot_answer(text: str, pending: SlotName | None = None) -> SlotName | None:
    """Classify which check-in slot the user answered, if any."""
    raw = (text or "").strip()
    if not raw:
        return None

    tokens = tokenize(raw)
    if not tokens:
        return None

    scores = _explicit_slot_scores(tokens, raw)
    explicit = _pick_highest_explicit_slot(scores)
    if explicit is not None:
        # Long narrative: symptom mention at the end must not auto-close wellness slot.
        if (
            explicit == SlotName.WELLNESS
            and len(tokens) >= _LONG_NARRATIVE_TOKEN_THRESHOLD
            and scores[SlotName.MOOD] == 0
            and scores[SlotName.SLEEP] == 0
            and scores[SlotName.PLANS] == 0
            and _any_token_matches_stems(tokens, WELLNESS_SYMPTOM_STEMS)
            and not _any_token_matches_stems(tokens, WELLNESS_TOPIC_STEMS)
        ):
            return None
        return explicit

    if pending is not None and is_generic_polarity_answer(tokens):
        return pending

    if pending is not None and len(tokens) <= 3:
        return pending

    return None


def slot_from_text(text: str) -> SlotName | None:
    """Explicit topic mention in user text (refusal / side context)."""
    tokens = tokenize(text)
    if not tokens:
        return None
    scores = _explicit_slot_scores(tokens, text)
    return _pick_highest_explicit_slot(scores)


def extract_symptom_code(text: str) -> str | None:
    """Body-location symptom from token boundaries (last matching token wins)."""
    tokens = tokenize(text)
    found: str | None = None
    for token in tokens:
        for stem, code in SYMPTOM_CODE_BY_STEM.items():
            if _stem_matches_token(token, stem):
                found = code
    return found


def extract_correction_symptom(text: str) -> str | None:
    """Symptom focus for explicit correction turns."""
    tokens = tokenize(text)
    low = text.lower()

    negated_head = bool(re.search(r"\bне\s+голов\w*\b", low))
    has_back = _any_token_matches_stems(tokens, ("спина", "спине", "спину", "спин"))
    has_head = _any_token_matches_stems(tokens, ("голова", "голову", "голове", "головой", "голов"))

    if has_back:
        return "back"
    if negated_head and not has_back:
        return "other"
    if has_head and not negated_head:
        return "head"

    return extract_symptom_code(text)
