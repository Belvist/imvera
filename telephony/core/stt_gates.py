"""Unified STT post-processing gates for every telephony path.

Confidence bar, vocabulary plausibility, and fall-miscue repair are applied
here so phone one-shot, streaming, and batch /turn paths behave the same.
"""
from __future__ import annotations

from core.vocab import looks_like_garbage, repair_fall_miscue

try:
    from core.dialogue import short_real_answer
except ImportError:  # pragma: no cover
    short_real_answer = lambda _t: None  # noqa: E731

CONF_GATE_LOW = 0.55
CONF_GATE_MID = 0.80


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
    if looks_like_garbage(text):
        print(f"[call-agent] vocab-gate: no recognizable word "
              f"({confidence}) -> anchor", flush=True)
        return "", "low_conf"
    if confidence is not None and confidence < CONF_GATE_MID:
        return text, "stt_uncertain"
    return text, None
