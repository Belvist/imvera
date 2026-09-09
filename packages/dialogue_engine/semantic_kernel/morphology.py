"""Russian morphology normalization — pymorphy3 when available, lightweight fallback."""

from __future__ import annotations

import re
from functools import lru_cache

_MORPH = None
_MORPH_TRIED = False


def _load_morph():
    global _MORPH, _MORPH_TRIED
    if _MORPH_TRIED:
        return _MORPH
    _MORPH_TRIED = True
    try:
        import pymorphy3

        _MORPH = pymorphy3.MorphAnalyzer()
    except ImportError:
        _MORPH = None
    return _MORPH


@lru_cache(maxsize=4096)
def normalize_token(token: str) -> str:
    """Lemma for a single token; falls back to lowercase when pymorphy absent."""
    raw = token.strip().lower()
    if not raw or not re.match(r"^[а-яё\-]+$", raw, re.I):
        return raw
    morph = _load_morph()
    if morph is not None:
        parsed = morph.parse(raw)
        if parsed:
            return parsed[0].normal_form
    return raw


def normalize_text(text: str) -> str:
    return " ".join(normalize_token(t) for t in re.findall(r"[а-яёa-z]+", text.lower(), re.I))
