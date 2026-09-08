"""Events — sole input to DialogueEngine.reduce."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from packages.dialogue_engine.semantic import SemanticTurn


class DialogueEvent(BaseModel):
    kind: str

    model_config = {"frozen": True}


class CallStarted(DialogueEvent):
    kind: Literal["call_started"] = "call_started"


class UserTurnReceived(DialogueEvent):
    kind: Literal["user_turn_received"] = "user_turn_received"
    turn_id: str
    text: str
    semantic: SemanticTurn | None = None
    effect_id: str = ""
    revision: int = 0


class InterpretationCompleted(DialogueEvent):
    kind: Literal["interpretation_completed"] = "interpretation_completed"
    turn_id: str
    effect_id: str
    semantic: SemanticTurn
    revision: int = 0


class PlayoutStarted(DialogueEvent):
    kind: Literal["playout_started"] = "playout_started"
    generation: int
    question_id: str
    effect_id: str = ""
    revision: int = 0


class PlayoutCompleted(DialogueEvent):
    kind: Literal["playout_completed"] = "playout_completed"
    generation: int
    question_id: str
    effect_id: str = ""
    revision: int = 0


class PlayoutCancelled(DialogueEvent):
    kind: Literal["playout_cancelled"] = "playout_cancelled"
    generation: int
    question_id: str = ""
    effect_id: str = ""
    revision: int = 0


class TimerExpired(DialogueEvent):
    kind: Literal["timer_expired"] = "timer_expired"
    timer_id: str = ""
    revision: int = 0


class DeliveryDeferred(DialogueEvent):
    kind: Literal["delivery_deferred"] = "delivery_deferred"
    effect_id: str
    revision: int = 0


class SpeakEffectStale(DialogueEvent):
    kind: Literal["speak_effect_stale"] = "speak_effect_stale"
    effect_id: str
    intent: str
    generation: int
    revision: int = 0


class EffectFailed(DialogueEvent):
    kind: Literal["effect_failed"] = "effect_failed"
    effect_id: str
    stage: Literal["TTS", "PLAYOUT", "TIMER"]
    error: str = ""
    revision: int = 0


class BotOpeningDelivered(DialogueEvent):
    kind: Literal["bot_opening_delivered"] = "bot_opening_delivered"
    question_id: str = "opening-1"


class User(DialogueEvent):
    kind: Literal["user"] = "user"
    text: str
    semantic: SemanticTurn | None = None
