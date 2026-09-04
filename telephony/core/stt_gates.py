"""Unified STT post-processing gates for every telephony path.

Confidence bar, vocabulary plausibility, and fall-miscue repair are applied
here so phone one-shot, streaming, and batch /turn paths behave the same.
"""
from __future__ import annotations

import re

from core.vocab import (
    looks_like_garbage,
    looks_like_stt_glue_noise,
    repair_fall_miscue,
)

try:
    from conversation_system.turn._cleaners import short_real_answer
except ImportError:  # pragma: no cover
    short_real_answer = lambda _t: None  # noqa: E731

CONF_GATE_LOW = 0.55
CONF_GATE_MID = 0.80
# Mid-band confirm only for short/ambiguous lines (live 727fdf: «Ничего не
# нужно» @0.78 must not loop «Я правильно услышала?»).
CONF_UNCERTAIN_MAX = 0.72
_CLEAR_UTTERANCE_RE = re.compile(
    r"(ничего\s+не\s+(?:нуж|надо)|не\s+(?:надо|нужно)|"
    r"вс[её]\s+(?:норм|хорош)|нормально|"
    r"да,?\s*(?:правильно|верно|всё\s+верно)|"
    r"пойд[её]т|более[\s-]*мен|легче|лучше|отпустило|"
    r"хорош\w*\s+настроени|настроени\w*\s+хорош|"
    r"чувствую\s+себя\s+хорош)",
    re.I)


def _skip_uncertain_confirm(text: str, confidence: float | None) -> bool:
    """Skip «Я правильно услышала?» for clear multi-word answers."""
    t = (text or "").strip()
    if not t:
        return False
    if short_real_answer(t):
        return True
    if _CLEAR_UTTERANCE_RE.search(t):
        return True
    words = len(t.split())
    if words >= 3 and confidence is not None and confidence >= CONF_UNCERTAIN_MAX:
        return True
    if words >= 5 and not looks_like_garbage(t):
        return True
    return False


def gate_stt_transcript(transcript, confidence):
    """Return ``(text, reason)`` after gates.

    * ``text`` — cleaned transcript, or ``""`` when the turn is rejected;
    * ``reason`` — ``None``, ``"low_conf"``, or ``"stt_uncertain"`` for the
      dialogue empty/confirm ladder.
    """
    text = (transcript or "").strip()
    if not text:
        return "", None
    text = repair_fall_miscue(text)
    # Phone one-word wellness answers survive a noisy confidence score.
    if short_real_answer(text):
        return text, None
    if confidence is not None and confidence < CONF_GATE_LOW:
        print(f"[call-agent] low-conf transcript "
              f"({confidence:.2f}) -> repeat request", flush=True)
        return "", "low_conf"
    if looks_like_garbage(text) or looks_like_stt_glue_noise(text):
        print(f"[call-agent] vocab-gate: implausible caller speech "
              f"({confidence}) -> anchor", flush=True)
        return "", "low_conf"
    if confidence is not None and confidence < CONF_GATE_MID:
        if _skip_uncertain_confirm(text, confidence):
            return text, None
        return text, "stt_uncertain"
    return text, None
