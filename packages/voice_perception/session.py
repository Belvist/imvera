"""Per-call perception session — uplink gate, turn FSM, preroll, downlink reference."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.voice_perception.config import PerceptionConfig
from packages.voice_perception.echo_ref_gate import EchoRefConfig, EchoVerdict
from packages.voice_perception.playback_reference import EchoClassification, PlaybackReference
from packages.voice_perception.text_echo import is_text_echo_of_bot, normalize_speech_text
from packages.voice_perception.turn_fsm import ConversationPhase, TurnManager


@dataclass(frozen=True)
class UplinkDecision:
    """What CallActor should do with one uplink PCM frame."""

    feed_vad: bool
    append_preroll: bool
    blocked: bool = False
    buffer_only: bool = False
    echo_verdict: EchoVerdict | None = None
    echo_score: float = 0.0


@dataclass
class PerceptionSession:
    """Owns perception state for one call — in-process or behind imvera_perception service."""

    config: PerceptionConfig
    turn_manager: TurnManager = field(default_factory=TurnManager)
    _playback_ref: PlaybackReference | None = None
    _uplink_preroll_buf: bytearray = field(default_factory=bytearray)
    _blocked_preroll_pending: bytes = b""
    _listen_gated_until: float | None = None

    @property
    def playback_ref(self) -> PlaybackReference | None:
        return self._playback_ref

    def ensure_playback_ref(self) -> None:
        if not self.config.echo_ref_gate:
            self._playback_ref = None
            return
        if self._playback_ref is None:
            self._playback_ref = PlaybackReference(
                EchoRefConfig(sample_rate=self.config.sample_rate)
            )

    def push_downlink(self, pcm_s16le: bytes) -> None:
        if not self.config.echo_ref_gate or not pcm_s16le:
            return
        self.ensure_playback_ref()
        if self._playback_ref is not None:
            self._playback_ref.push(pcm_s16le)

    def on_playback_started(self, intent: str) -> None:
        self.turn_manager.on_playback_started(
            intent,
            barge_in_enabled=bool(self.config.lab_barge_in),
        )

    def on_playback_completed(self, now_mono: float) -> None:
        self.turn_manager.on_playback_completed(now_mono)

    def on_listen_enabled(self) -> int:
        """Snapshot blocked-period uplink for utterance preroll; keep playback ref."""
        self._blocked_preroll_pending = bytes(self._uplink_preroll_buf)
        self._uplink_preroll_buf.clear()
        return len(self._blocked_preroll_pending)

    @property
    def blocked_preroll_pending(self) -> bytes:
        return self._blocked_preroll_pending

    def consume_blocked_preroll(self) -> bytes:
        pending = self._blocked_preroll_pending
        self._blocked_preroll_pending = b""
        return pending

    def arm_post_speech_pause(self, now_mono: float) -> None:
        if not self.config.lab_half_duplex:
            self._listen_gated_until = None
            return
        pause_ms = max(0, min(2000, int(self.config.post_speech_pause_ms)))
        if pause_ms <= 0:
            self._listen_gated_until = None
            return
        self._listen_gated_until = now_mono + (pause_ms / 1000.0)

    def force_listen_enabled(self) -> None:
        self._listen_gated_until = None
        self.turn_manager.phase = ConversationPhase.LISTENING
        self.turn_manager._echo_tail_until = None

    def uplink_listen_blocked(self, *, playback_active: bool, now_mono: float) -> bool:
        if self.config.lab_half_duplex:
            if playback_active:
                return True
            until = self._listen_gated_until
            if until is None:
                return False
            if now_mono >= until:
                self._listen_gated_until = None
                return False
            return True
        if playback_active and not self.config.echo_ref_gate:
            return True
        return False

    def tick(self, now_mono: float) -> None:
        self.turn_manager.tick(now_mono)

    def process_uplink(
        self,
        pcm: bytes,
        *,
        playback_active: bool,
        now_mono: float,
    ) -> UplinkDecision:
        self.tick(now_mono)
        blocked = self.uplink_listen_blocked(
            playback_active=playback_active,
            now_mono=now_mono,
        )
        buffer_only = self.turn_manager.should_buffer_only()
        if blocked or buffer_only or not self.turn_manager.should_feed_vad():
            self._append_preroll(pcm)
            return UplinkDecision(
                feed_vad=False,
                append_preroll=True,
                blocked=blocked,
                buffer_only=buffer_only,
            )

        if self.config.echo_ref_gate:
            self.ensure_playback_ref()
            if self._playback_ref is not None:
                classification = self._playback_ref.classify(
                    pcm, playback_active=playback_active
                )
                if self._should_drop_echo_for_vad(classification):
                    append = classification.verdict != EchoVerdict.ECHO
                    if append:
                        self._append_preroll(pcm)
                    return UplinkDecision(
                        feed_vad=False,
                        append_preroll=append,
                        echo_verdict=classification.verdict,
                        echo_score=classification.score,
                    )

        return UplinkDecision(feed_vad=True, append_preroll=False)

    def classify_uplink_echo(
        self, pcm: bytes, *, playback_active: bool
    ) -> EchoClassification | None:
        if not self.config.echo_ref_gate:
            return None
        self.ensure_playback_ref()
        if self._playback_ref is None:
            return None
        return self._playback_ref.classify(pcm, playback_active=playback_active)

    def should_suppress_speech_start(
        self, pcm: bytes, *, playback_active: bool
    ) -> bool:
        echo_verdict: EchoVerdict | None = None
        if self.config.echo_ref_gate and self._playback_ref is not None:
            echo_verdict = self._playback_ref.classify(
                pcm, playback_active=playback_active
            ).verdict
        return self.turn_manager.should_suppress_speech_start(
            playback_active=playback_active,
            echo_verdict=echo_verdict,
        )

    def is_assistant_text_echo(
        self,
        text: str,
        bot_candidates: list[str],
        *,
        allowlist: frozenset[str] | None = None,
    ) -> bool:
        normalized = normalize_speech_text(text)
        if not normalized:
            return True
        if allowlist and normalized in allowlist:
            return False
        for phrase in bot_candidates:
            if is_text_echo_of_bot(text, phrase, allowlist=allowlist):
                return True
            spoken = normalize_speech_text(phrase)
            if not spoken:
                continue
            if normalized == spoken:
                return True
            if len(normalized) >= 6 and (spoken in normalized or normalized in spoken):
                return True
            user_tokens = normalized.split()
            spoken_tokens = spoken.split()
            if user_tokens and spoken_tokens[: len(user_tokens)] == user_tokens:
                if len(user_tokens) >= 2 or len(user_tokens[0]) >= 4:
                    return True
        return False

    def _append_preroll(self, pcm: bytes) -> None:
        cap_ms = int(self.config.uplink_preroll_ms)
        if cap_ms <= 0 or not pcm:
            return
        max_bytes = self.config.sample_rate * 2 * cap_ms // 1000
        self._uplink_preroll_buf.extend(pcm)
        overflow = len(self._uplink_preroll_buf) - max_bytes
        if overflow > 0:
            del self._uplink_preroll_buf[:overflow]

    @staticmethod
    def _should_drop_echo_for_vad(classification: EchoClassification) -> bool:
        if classification.verdict == EchoVerdict.ECHO:
            return True
        if classification.verdict == EchoVerdict.UNCERTAIN and classification.playback_active:
            return True
        return False
