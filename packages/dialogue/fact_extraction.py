"""Clause-aware fact extraction — multiple fields per utterance."""

import re

from packages.contracts.interpretation import FactCandidate

_SLEEP = re.compile(r"\b(спал\w*|сон\w*|не\s+спал\w*|плохо\s+спал\w*|хорошо\s+спал\w*)\b", re.I)
_PLANS = re.compile(r"\b(дома|врач\w*|нигде|гуля\w*|магазин\w*|внук\w*|буду\s+дома)\b", re.I)
_WELLNESS = re.compile(
    r"\b(нормально|хорошо|отлично|плохо|нехорошо|болит|устал\w*|слаб\w*|"
    r"голов\w*|температур\w*|чувствую\s+себя|мне\s+плохо|мне\s+нехорошо)\b",
    re.I,
)
_WELLNESS_POSITIVE = re.compile(
    r"(чувствую\s+себя\s+(хорошо|нормально|отлично)|отлично|"
    r"пока\s+вс[её]\s+хорошо|вс[её]\s+хорошо|не\s+плохо)",
    re.I,
)
_MOOD = re.compile(r"\b(настроен\w*|грустн\w*|весел\w*|радост\w*|подавлен\w*)\b", re.I)
_NARRATIVE = re.compile(
    r"\b(фильм|сериал|сосед\w*|вчера\s+смотрел\w*|приходил\w*|гост\w*)\b",
    re.I,
)
_CORRECTION = re.compile(r"\b(нет|не\s+так|исправ\w*|имел\w*\s+в\s+виду)\b", re.I)


def _clauses(text: str) -> list[str]:
    parts = re.split(r"[,;]|\s+а\s+|\s+но\s+|\s+только\s+", text, flags=re.I)
    return [p.strip() for p in parts if p.strip()]


def _classify_clause(clause: str, pending_slot: str | None) -> str | None:
    lower = clause.lower()
    if _NARRATIVE.search(lower) and not (_WELLNESS.search(lower) or _SLEEP.search(lower)):
        return None
    if _SLEEP.search(lower):
        return "sleep"
    if _PLANS.search(lower):
        return "plans"
    if _WELLNESS_POSITIVE.search(lower) or (
        _WELLNESS.search(lower) and not _MOOD.search(lower)
    ):
        return "wellness"
    if _MOOD.search(lower):
        return "mood"
    if pending_slot and len(lower.split()) <= 4:
        short_ok = {
            "wellness": _WELLNESS.search(lower) or lower in {"нормально", "хорошо", "отлично"},
            "mood": _MOOD.search(lower) or lower in {"хорошо", "нормально", "грустно"},
            "sleep": _SLEEP.search(lower),
            "plans": _PLANS.search(lower) or lower in {"дома", "нигде"},
        }
        if short_ok.get(pending_slot):
            return pending_slot
    return None


def extract_fact_candidates(
    text: str,
    pending_slot: str | None = None,
) -> list[FactCandidate]:
    """Extract zero or more fact candidates from free text."""
    seen: dict[str, FactCandidate] = {}
    is_correction = bool(_CORRECTION.search(text.lower()))

    for clause in _clauses(text):
        field = _classify_clause(clause, pending_slot)
        if not field:
            continue
        seen[field] = FactCandidate(
            field=field,
            value=clause.strip(),
            source_quote=clause.strip(),
            answers_pending=field == pending_slot if pending_slot else False,
            negated=bool(re.search(r"\bне\s+", clause.lower())),
        )

    if not seen and pending_slot:
        field = _classify_clause(text, pending_slot)
        if field:
            seen[field] = FactCandidate(
                field=field,
                value=text.strip(),
                source_quote=text.strip(),
                answers_pending=True,
            )

    candidates = list(seen.values())
    if is_correction and candidates:
        for c in candidates:
            c.answers_pending = True
    return candidates
