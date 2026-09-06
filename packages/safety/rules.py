"""Deterministic safety pattern matching (Russian) with context."""

import re

RED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("fall", re.compile(r"\b(упал[аио]?|упала|упали|падени[ея])\b", re.I)),
    ("cannot_stand", re.compile(r"\b(не\s+могу\s+(встать|подняться))\b", re.I)),
    ("help_urgent", re.compile(r"\b(помогите|спасите|вызывайте\s+скорую)\b", re.I)),
    ("severe_pain", re.compile(r"\b(очень\s+больно|сильн[аяое]+\s+боль)\b", re.I)),
]

YELLOW_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("dizziness", re.compile(r"\b(голова\s+круж\w*|кружится\s+голова)\b", re.I)),
    (
        "feels_bad",
        re.compile(
            r"\b(мне\s+плохо|плохо\s+себя\s+чувств\w*|чувств\w*\s+себя\s+плохо)\b",
            re.I,
        ),
    ),
]

_THIRD_PARTY = re.compile(
    r"\b(сосед\w*|внук\w*|внучк\w*|дочь|сын|мама|папа|брат|сестр\w*|родственник\w*)\b",
    re.I,
)
_PAST_EVENT = re.compile(r"\b(вчера|позавчера|на\s+прошлой\s+неделе|раньше|давно)\b", re.I)
_SELF = re.compile(r"\b(я|мне|меня)\b", re.I)


def _negation_before(text: str, match_start: int) -> bool:
    prefix = text[:match_start].rstrip()
    if re.search(r"\bне\s*$", prefix):
        return True
    tokens = prefix.split()
    if tokens and tokens[-1] in ("не", "ни", "никогда"):
        return True
    if len(tokens) >= 2 and tokens[-2] == "не":
        return True
    return False


def _is_third_party_event(text: str, match_start: int) -> bool:
    """Another person's event — not the elder's current situation."""
    if not _THIRD_PARTY.search(text):
        return False
    if _SELF.search(text[: match_start + 1]):
        return False
    return True


def _is_past_reported_event(text: str) -> bool:
    """Past narrative about someone else (e.g. «вчера соседка упала»)."""
    return bool(_PAST_EVENT.search(text) and _THIRD_PARTY.search(text))


def _match_signal(pattern: re.Pattern[str], text: str, signal_id: str) -> bool:
    match = pattern.search(text)
    if not match:
        return False
    if signal_id == "fall":
        if _is_past_reported_event(text):
            return False
        if _is_third_party_event(text, match.start()):
            return False
        if _negation_before(text, match.start()):
            return False
    return True


def match_deterministic_signals(text: str) -> list[str]:
    """Return signal ids found in normalized transcript."""
    if not text or not text.strip():
        return []
    normalized = text.lower().strip()
    found: list[str] = []
    for signal_id, pattern in RED_PATTERNS + YELLOW_PATTERNS:
        if _match_signal(pattern, normalized, signal_id):
            found.append(signal_id)
    return found


def signal_to_risk_level(signal_id: str) -> str:
    for sid, _ in RED_PATTERNS:
        if sid == signal_id:
            return "RED"
    return "YELLOW"
