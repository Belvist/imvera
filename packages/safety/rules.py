"""Deterministic safety pattern matching (Russian) with per-clause context."""

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
_CLAUSE_SPLIT = re.compile(r"[,;]|\s+но\s+|\s+а\s+", re.I)


def _split_clauses(text: str) -> list[str]:
    parts = _CLAUSE_SPLIT.split(text.lower().strip())
    return [part.strip() for part in parts if part.strip()]


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


def _fall_applies_in_clause(clause: str, match_start: int) -> bool:
    if _negation_before(clause, match_start):
        return False
    if _SELF.search(clause):
        return True
    if _THIRD_PARTY.search(clause) and not _SELF.search(clause):
        if _PAST_EVENT.search(clause):
            return False
        return False
    return True


def _match_signal_in_clause(
    pattern: re.Pattern[str],
    clause: str,
    signal_id: str,
) -> bool:
    match = pattern.search(clause)
    if not match:
        return False
    if signal_id == "fall":
        return _fall_applies_in_clause(clause, match.start())
    return True


def match_deterministic_signals(text: str) -> list[str]:
    """Return signal ids found in normalized transcript (clause-aware)."""
    if not text or not text.strip():
        return []
    found: list[str] = []
    clauses = _split_clauses(text)
    if not clauses:
        clauses = [text.lower().strip()]
    for clause in clauses:
        for signal_id, pattern in RED_PATTERNS + YELLOW_PATTERNS:
            if _match_signal_in_clause(pattern, clause, signal_id):
                if signal_id not in found:
                    found.append(signal_id)
    return found


def signal_to_risk_level(signal_id: str) -> str:
    for sid, _ in RED_PATTERNS:
        if sid == signal_id:
            return "RED"
    return "YELLOW"
