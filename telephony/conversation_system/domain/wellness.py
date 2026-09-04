"""Wellness band classification — drives adaptive flow and closing behavior."""
from __future__ import annotations

import re
from enum import Enum
from typing import Tuple

from conversation_system.agenda.topics import BAD_WORDS, OK_WORDS


class WellnessBand(str, Enum):
    """Caller wellness state after initial listen — not a safety verdict."""

    UNKNOWN = "unknown"
    GOOD = "good"
    MEDIUM = "medium"
    BAD = "bad"
    CRITICAL = "critical"


# Patterns that indicate critical state (fast close, no dragging).
_CRITICAL_PATTERNS: Tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bупал\b",
        r"\bупала\b",
        r"\bне\s+дыш",
        r"\bзадыха",
        r"\bочень\s+плох",
        r"\bскор\w*\s+нужн",
        r"\bвызов\w*\s+(?:скор\w*|помощ)",
        r"\bпомог\w*\s+(?:мне|срочно)",
        r"\bне\s+мог\w*\s+(?:встать|двиг|дыш)",
    )
)

# Medium: vague / uncertain wellness — neither clearly good nor bad.
_MEDIUM_PATTERNS: Tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bне\s+очень\b",
        r"\bтак\s+себе\b",
        r"\bсредне\b",
        r"\bнормальн\w*\s+так",
        r"\bничего\s+особенн",
        r"\bкак\s+обычн",
        r"\bтерпимо\b",
        r"\bне\s+жалуюсь\b",
    )
)


_UNRELIABLE_WELLNESS_BLEED_RE = re.compile(
    r"\b(сука|суки|бля|блять|нахуй|пизд|хуй|ёб|еба|ебан|кикули)\b",
    re.IGNORECASE,
)


def _unreliable_wellness_context(text: str) -> bool:
    """Embedded «неплохо» in profane/TV bleed must not advance wellness."""
    low = (text or "").lower()
    if _UNRELIABLE_WELLNESS_BLEED_RE.search(low):
        return True
    if re.search(r"\b(тебя|тебе|ты)\b", low) and len(low.split()) >= 5:
        return not _has_symptom_signal(text)
    return False


def _has_ok_signal(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in OK_WORDS)


def _has_bad_signal(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in BAD_WORDS)


def _matches_any(text: str, patterns: Tuple[re.Pattern[str], ...]) -> bool:
    return any(p.search(text) for p in patterns)


def _negated_before(text: str, root: str) -> bool:
    """True when «не» immediately precedes a critical root (e.g. «я не упал»)."""
    low = text.lower()
    for m in re.finditer(rf"\b{re.escape(root)}\w*\b", low):
        start = m.start()
        window = low[max(0, start - 12):start]
        if re.search(r"\bне\s*$", window):
            return True
    return False


def _has_negated_symptom(text: str) -> bool:
    """«ничего не болело», «не болит» with positive context — not a complaint."""
    low = text.lower()
    if re.search(r"ничего\s+(?:сегодня\s+)?не\s+бол", low):
        return True
    for root in ("болит", "болел", "болела", "болеет"):
        if _negated_before(low, root):
            return True
    return False


def _has_symptom_signal(text: str) -> bool:
    """Symptom keywords that are not negated."""
    if _has_negated_symptom(text):
        return False
    low = text.lower()
    return bool(re.search(
        r"голов|болит|болел|болела|болеет|тошн|ташн|круж|давлен|"
        r"температур|слабост|недомог|сердц|дыш|кашл",
        low,
    ))


def classify_wellness(text: str) -> WellnessBand:
    """Classify caller wellness from transcript after greeting listen."""
    cleaned = (text or "").strip()
    if not cleaned:
        return WellnessBand.UNKNOWN

    if _unreliable_wellness_context(cleaned):
        return WellnessBand.UNKNOWN

    low = cleaned.lower()
    if _negated_before(low, "упал") or _negated_before(low, "упала"):
        return WellnessBand.GOOD

    if _matches_any(cleaned, _CRITICAL_PATTERNS):
        if _negated_before(low, "упал") or _negated_before(low, "упала"):
            pass  # negated fall — not critical wellness
        else:
            return WellnessBand.CRITICAL
    if _has_ok_signal(cleaned) and not _has_symptom_signal(cleaned):
        return WellnessBand.GOOD

    if _matches_any(cleaned, _MEDIUM_PATTERNS):
        return WellnessBand.MEDIUM

    if _has_symptom_signal(cleaned):
        return WellnessBand.BAD

    if _has_bad_signal(cleaned):
        return WellnessBand.BAD

    if _has_ok_signal(cleaned):
        return WellnessBand.GOOD

    return WellnessBand.UNKNOWN


def good_path_probe_count() -> int:
    """Number of simple state-check questions on GOOD path (product spec: 2–3)."""
    return 3


def bad_path_probe_count() -> int:
    """Symptom depth on BAD path: severity + timing + follow-up before notify."""
    return 3


_SYMPTOM_INTENSIFIERS: frozenset[str] = frozenset((
    "сильно", "очень", "невыносимо", "непереносимо", "сильная", "сильнее",
    "невыносимая", "ужасно", "мучительно", "нестерпимо", "невыносим",
))


def is_symptom_intensifier(text: str) -> bool:
    """Single-word or pure intensifier answer to symptom depth probe."""
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return False
    words = re.findall(r"[а-яёa-z]+", cleaned)
    return bool(words) and all(w in _SYMPTOM_INTENSIFIERS for w in words)


def closing_requires_fast_exit(band: WellnessBand) -> bool:
    """Critical band closes immediately — no extra probing."""
    return band == WellnessBand.CRITICAL
