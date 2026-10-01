"""Side effects — executed by CallActor, never applied inside reducer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Effect(BaseModel):
    kind: str
    effect_id: str = ""
    revision: int = 0

    model_config = {"frozen": True}


class SpeakEffect(Effect):
    kind: Literal["speak"] = "speak"
    generation_id: str
    generation: int
    text: str
    intent: str
    question_id: str = ""
    slot: str | None = None
    marks_question: bool = False
    semantic_scope_id: str = ""
    supersedes_effect_id: str = ""
    reissue_count: int = 0
    # Pre-join spans retained for delivery trace. ADR-025 retired generative
    # bridge rewriting: the complete canonical text always goes to TTS.
    bridge_text: str = ""
    question_text: str = ""
    bridge_llm_allowed: bool = False  # Historical serialized field; never consulted.


class InterpretEffect(Effect):
    kind: Literal["interpret"] = "interpret"
    turn_id: str
    text: str


class TimerEffect(Effect):
    kind: Literal["timer"] = "timer"
    timer_id: str
    wait_ms: int
    reason: str = "answer_wait"
    semantic_scope_id: str = ""


class EndCallEffect(Effect):
    kind: Literal["end_call"] = "end_call"
    reason: str = ""


# Backward alias
HangupEffect = EndCallEffect

ENGINE_SPEAK_INTENTS = frozenset(
    {
        "opening_wellness",
        "ack_wellness",
        "repair_repeat",
        "partial_unresolved_close",
        "summary",
        "urgent_close",
        "goodbye_confirm",
        "goodbye_final",
    }
) | frozenset({f"check_{s}" for s in ("wellness", "mood", "sleep", "plans")}) | frozenset(
    {f"clarify_{s}" for s in ("wellness", "mood", "sleep", "plans")}
) | frozenset({f"probe_{s}" for s in ("concern", "duration", "pain_night")})
