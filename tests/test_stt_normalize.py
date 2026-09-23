"""Tests for IMVERA STT wrapper layer (normalize + critical terms)."""

from __future__ import annotations

from services.stt.critical_terms import match_critical_terms
from services.stt.normalize import normalize_transcript


def test_niotin_maps_to_ne_ochen() -> None:
    assert normalize_transcript("Ниотин") == "не очень"
    assert normalize_transcript("Ниотин.") == "не очень"


def test_unrelated_text_unchanged() -> None:
    assert normalize_transcript("Хорошо.") == "Хорошо."
    assert normalize_transcript("помогите") == "помогите"


def test_critical_terms_safety() -> None:
    hits = match_critical_terms("Мне плохо, помогите")
    terms = {h["term"] for h in hits}
    assert "мне плохо" in terms
    assert "помогите" in terms


def test_critical_terms_empty() -> None:
    assert match_critical_terms("") == []
    assert match_critical_terms("хорошо") == []


def test_endpointing_truncations_completed() -> None:
    """Live endpointing cuts single-token answers («Пло.») — complete them,
    they are unambiguous in isolation."""
    assert normalize_transcript("Пло.") == "плохо"
    assert normalize_transcript("Пло") == "плохо"
    assert normalize_transcript("Хоро.") == "хорошо"
