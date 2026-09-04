"""First-call consent dialogue — no legacy Agent dependency."""
from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from core.consent import (
    CONSENT_VOICE_SCRIPT,
    apply_consent_outcome,
    classify_consent_reply,
)

if TYPE_CHECKING:
    from core.call_mirror import CallMirror


def start_consent_call(mirror: "CallMirror") -> str:
    """Enter consent mode; return the voice script for Lua greeting."""
    mirror._consent_call = True
    mirror._consent_empty = 0
    mirror._consent_granted = False
    mirror._consent_declined = False
    mirror.status = "unknown"
    return CONSENT_VOICE_SCRIPT


def plan_consent_turn(
    mirror: "CallMirror",
    caller_text: str = "",
    *,
    reason: str | None = None,
) -> Dict[str, Any]:
    """Return legacy-shaped plan dict for orchestrator TTS path."""
    text = (caller_text or "").strip()
    if not text or reason in ("low_conf", "echo", "stt_uncertain"):
        mirror._consent_empty += 1
        empty = mirror._consent_empty
        text_for_class = ""
    else:
        empty = mirror._consent_empty
        text_for_class = text
    decision, reply = classify_consent_reply(
        text=text_for_class, empty_turns=empty)
    apply_consent_outcome(
        mirror,
        decision,
        pg=getattr(mirror, "_pg", None),
        person_id=getattr(mirror, "_person_id", None),
        method="voice",
        household_id=getattr(mirror, "_household_id", None),
    )
    if decision == "pending" and empty == 0 and not text_for_class:
        reply = CONSENT_VOICE_SCRIPT
    if decision != "pending":
        mirror.done = True
    return {
        "text": caller_text or "",
        "intent": None,
        "fallback": reply,
        "terminal": decision != "pending",
        "scripted": True,
        "allow_llm": False,
    }
