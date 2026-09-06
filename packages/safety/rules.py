"""Deterministic safety pattern matching (Russian)."""

import re

# Unconditional RED roots — fall, explicit help, severe pain patterns
RED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("fall", re.compile(r"\b(упал[аио]?|упала|упали|падени[ея])\b", re.I)),
    ("cannot_stand", re.compile(r"\b(не\s+могу\s+(встать|подняться|встать))\b", re.I)),
    ("help_urgent", re.compile(r"\b(помогите|спасите|вызывайте\s+скорую)\b", re.I)),
    ("severe_pain", re.compile(r"\b(очень\s+больно|сильн[аяое]+\s+боль)\b", re.I)),
]

YELLOW_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("dizziness", re.compile(r"\b(голова\s+круж\w*|кружится\s+голова)\b", re.I)),
    ("feels_bad", re.compile(r"\b(мне\s+плохо|плохо\s+себя\s+чувств)\b", re.I)),
]


def match_deterministic_signals(text: str) -> list[str]:
    """Return signal ids found in normalized transcript."""
    if not text or not text.strip():
        return []
    normalized = text.lower().strip()
    found: list[str] = []
    for signal_id, pattern in RED_PATTERNS + YELLOW_PATTERNS:
        if pattern.search(normalized):
            found.append(signal_id)
    return found


def signal_to_risk_level(signal_id: str) -> str:
    for sid, _ in RED_PATTERNS:
        if sid == signal_id:
            return "RED"
    return "YELLOW"
