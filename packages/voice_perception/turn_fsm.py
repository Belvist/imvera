"""Conversation turn FSM — single owner for listen / speak / echo-tail phases."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from packages.voice_perception.echo_ref_gate import EchoVerdict


class ConversationPhase(StrEnum):
    BOT_SPEAKING = "bot_speaking"
    ECHO_TAIL = "echo_tail"
    LISTENING = "listening"
    USER_SPEAKING = "user_speaking"
    PROCESSING = "processing"
    BARGE_IN_CANDIDATE = "barge_in_candidate"


class TurnPolicyKind(StrEnum):
    OPENING = "opening"
    NORMAL = "normal"
    CRITICAL_CONFIRMATION = "critical_confirmation"


@dataclass(frozen=True)
class TurnPolicy:
    kind: TurnPolicyKind
    barge_in: bool
    echo_tail_ms: int
    buffer_during_bot_speech: bool
    allow_stt_during_bot: bool


_OPENING_INTENTS = frozenset(
    {
        "opening_wellness",
        "greeting",
        "identity_intro",
    }
)
_CRITICAL_INTENTS = frozenset(
    {
        "confirm_identity",
        "confirm_consent",
    }
)


def policy_for_intent(intent: str, *, barge_in_enabled: bool) -> TurnPolicy:
    if intent in _OPENING_INTENTS:
        return TurnPolicy(
            kind=TurnPolicyKind.OPENING,
            barge_in=False,
            echo_tail_ms=450,
            buffer_during_bot_speech=True,
            allow_stt_during_bot=False,
        )
    if intent in _CRITICAL_INTENTS:
        return TurnPolicy(
            kind=TurnPolicyKind.CRITICAL_CONFIRMATION,
            barge_in=False,
            echo_tail_ms=450,
            buffer_during_bot_speech=True,
            allow_stt_during_bot=False,
        )
    return TurnPolicy(
        kind=TurnPolicyKind.NORMAL,
        barge_in=barge_in_enabled,
        echo_tail_ms=400,
        buffer_during_bot_speech=False,
        allow_stt_during_bot=False,
    )


@dataclass
class TurnManager:
    """Owns conversation phase transitions for one call."""

    phase: ConversationPhase = ConversationPhase.LISTENING
    policy: TurnPolicy = field(
        default_factory=lambda: policy_for_intent("", barge_in_enabled=False)
    )
    _echo_tail_until: float | None = None
    _barge_in_started_mono: float | None = None

    def on_playback_started(self, intent: str, *, barge_in_enabled: bool) -> None:
        self.policy = policy_for_intent(intent, barge_in_enabled=barge_in_enabled)
        self.phase = ConversationPhase.BOT_SPEAKING
        self._echo_tail_until = None
        self._barge_in_started_mono = None

    def on_playback_completed(self, now_mono: float) -> None:
        tail_ms = max(0, int(self.policy.echo_tail_ms))
        if tail_ms > 0:
            self.phase = ConversationPhase.ECHO_TAIL
            self._echo_tail_until = now_mono + (tail_ms / 1000.0)
        else:
            self.phase = ConversationPhase.LISTENING
            self._echo_tail_until = None

    def tick(self, now_mono: float) -> None:
        if (
            self.phase == ConversationPhase.ECHO_TAIL
            and self._echo_tail_until is not None
            and now_mono >= self._echo_tail_until
        ):
            self.phase = ConversationPhase.LISTENING
            self._echo_tail_until = None

    def echo_tail_remaining_s(self, now_mono: float) -> float:
        if self.phase != ConversationPhase.ECHO_TAIL or self._echo_tail_until is None:
            return 0.0
        return max(0.0, self._echo_tail_until - now_mono)

    def should_buffer_only(self) -> bool:
        if self.phase == ConversationPhase.ECHO_TAIL:
            return True
        if (
            self.phase == ConversationPhase.BOT_SPEAKING
            and self.policy.buffer_during_bot_speech
        ):
            return True
        return False

    def should_feed_vad(self) -> bool:
        if self.should_buffer_only():
            return False
        if self.phase == ConversationPhase.PROCESSING:
            return False
        return True

    def should_emit_utterance(self) -> bool:
        if self.phase in {
            ConversationPhase.ECHO_TAIL,
            ConversationPhase.BOT_SPEAKING,
            ConversationPhase.PROCESSING,
        }:
            return False
        return True

    def on_vad_speech_started(self, now_mono: float) -> None:
        if self.phase in {
            ConversationPhase.LISTENING,
            ConversationPhase.ECHO_TAIL,
            ConversationPhase.BOT_SPEAKING,
        }:
            self.phase = ConversationPhase.USER_SPEAKING

    def on_vad_speech_ended(self) -> None:
        if self.phase == ConversationPhase.USER_SPEAKING:
            self.phase = ConversationPhase.LISTENING

    def on_stt_submitted(self) -> None:
        self.phase = ConversationPhase.PROCESSING

    def on_turn_applied(self) -> None:
        self.phase = ConversationPhase.LISTENING

    def should_suppress_speech_start(
        self,
        *,
        playback_active: bool,
        echo_verdict: EchoVerdict | None,
    ) -> bool:
        if not playback_active:
            return False
        if self.policy.buffer_during_bot_speech:
            return True
        if self.policy.barge_in:
            if echo_verdict == EchoVerdict.USER:
                return False
            if self.phase == ConversationPhase.BARGE_IN_CANDIDATE:
                return False
            return True
        if echo_verdict == EchoVerdict.USER:
            return False
        return True

    def note_barge_in_candidate(self, now_mono: float) -> None:
        if self.policy.barge_in and self.phase == ConversationPhase.BOT_SPEAKING:
            self.phase = ConversationPhase.BARGE_IN_CANDIDATE
            self._barge_in_started_mono = now_mono

    def confirm_barge_in(self) -> None:
        if self.phase == ConversationPhase.BARGE_IN_CANDIDATE:
            self.phase = ConversationPhase.USER_SPEAKING
