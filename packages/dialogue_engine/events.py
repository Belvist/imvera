"""Events — sole input to DialogueEngine.reduce."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from packages.dialogue_engine.semantic import SemanticTurn
from packages.dialogue_engine.turn_understanding import RichUserTurn


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
    rich_turn: RichUserTurn | None = None
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
    # Uplink PCM frames received this call. None = unknown (tests, legacy
    # callers → old behavior). 0 = microphone dead/muted, not a silent
    # person — mic check, not reprompt/close.
    uplink_frames: int | None = None


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


class SafetyInterrupt(DialogueEvent):
    """SafetyEngine detector → DialogueEngine conversational owner."""

    kind: Literal["safety_interrupt"] = "safety_interrupt"
    level: Literal["RED", "YELLOW"] = "RED"
    quote: str = ""
    episode_id: str | None = None
    revision: int = 0


class FalseAlarmResolved(DialogueEvent):
    """False alarm confirmed → DialogueEngine leaves red handling and
    resumes the suspended obligation (COMMIT 4, separate semantic fix)."""

    kind: Literal["false_alarm_resolved"] = "false_alarm_resolved"
    episode_id: str | None = None
    revision: int = 0


class BotOpeningDelivered(DialogueEvent):
    kind: Literal["bot_opening_delivered"] = "bot_opening_delivered"
    question_id: str = "opening-1"


class User(DialogueEvent):
    kind: Literal["user"] = "user"
    text: str
    semantic: SemanticTurn | None = None
    rich_turn: RichUserTurn | None = None
