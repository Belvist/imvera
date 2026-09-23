"""Post-ASR normalization for known IMVERA mishearings (wrapper layer, not full ASR)."""

from __future__ import annotations

import re

# Extend after ADR-003 benchmark / live Zoiper traces — evidence-based only.
_WHOLE_PHRASE_FIXES: dict[str, str] = {
    "ниотин": "не очень",
    "ниотин.": "не очень",
    "неотин": "не очень",
    "не отин": "не очень",
    "нэ очень": "не очень",
    "не оч": "не очень",
    # Live endpointing truncations (single-token answers cut mid-word).
    "пло.": "плохо",
    "пло": "плохо",
    "хоро.": "хорошо",
    "хоро": "хорошо",
}

_SUBSTRING_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bниотин\w*\b", re.I), "не очень"),
)


def _normalize_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def normalize_transcript(text: str) -> str:
    """Map known ASR errors to expected wellness/safety phrases."""
    if not text or not text.strip():
        return text

    stripped = text.strip()
    whole = _WHOLE_PHRASE_FIXES.get(_normalize_key(stripped))
    if whole is not None:
        return whole

    out = stripped
    for pattern, replacement in _SUBSTRING_FIXES:
        out = pattern.sub(replacement, out)
    return out.strip()
