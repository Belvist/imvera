"""Match ADR-003 safety terms in normalized transcript."""

from __future__ import annotations

import re

from services.stt.vocabulary import IMVERA_CRITICAL_TERMS

_TERM_PATTERNS: dict[str, re.Pattern[str]] = {
    "упала": re.compile(r"\bупал[аио]?\b", re.I),
    "упал": re.compile(r"\bупал\b", re.I),
    "не могу встать": re.compile(r"\bне\s+могу\s+(встать|подняться)\b", re.I),
    "помогите": re.compile(r"\b(помогите|спасите)\b", re.I),
    "голова кружится": re.compile(r"\b(голова\s+круж\w*|кружится\s+голова)\b", re.I),
    "мне плохо": re.compile(r"\bмне\s+плохо\b", re.I),
    "скорая": re.compile(r"\bскор\w*\b", re.I),
}


def match_critical_terms(text: str) -> list[dict[str, object]]:
    """Return critical term hits for STT contract (matched=True only)."""
    if not text or not text.strip():
        return []

    hits: list[dict[str, object]] = []
    for term in IMVERA_CRITICAL_TERMS:
        pattern = _TERM_PATTERNS.get(term)
        if pattern is None:
            continue
        if pattern.search(text):
            hits.append({"term": term, "matched": True, "logprob": None})
    return hits
