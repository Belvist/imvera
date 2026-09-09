"""Per-call voice actor — media-ready greeting, render path, barge-in, lifecycle."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
import wave
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from packages.contracts.core import TerminationReason
from packages.contracts.enums import AsrQuality
from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.outbox import ActionOutboxStatus
from packages.contracts.providers import TTSProvider
from packages.contracts.runtime import RuntimeEvent, RuntimeEventType
from packages.contracts.turn import TurnProposal
from packages.dialogue.context_builder import active_question_kind, build_turn_context
from packages.dialogue.interpretation import to_turn_interpretation
from packages.dialogue.planner import Planner
from packages.dialogue.semantic_adapter import adapt_semantic_turn
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue.validator import Validator
from packages.dialogue_engine.context import InterpretContext
from packages.dialogue_engine.contextual_interpreter import contextual_interpret
from packages.dialogue_engine.effects import (
    ENGINE_SPEAK_INTENTS,
    EndCallEffect,
    SpeakEffect,
    TimerEffect,
)
from packages.dialogue_engine.fast_interpreter import fast_interpret_semantic
from packages.dialogue_engine.issue_mention_extract import should_use_rich_turn
from packages.dialogue_engine.semantic import semantic_to_interpretation
from packages.dialogue_engine.topic_tracker import is_topic_slot
from packages.dialogue_engine.turn_understanding import payload_to_rich_turn
from packages.voice_perception.config import PerceptionConfig
from packages.voice_perception.session import PerceptionSession
from packages.voice_perception.text_echo import text_echo_similarity
from packages.voice_runtime.agent_debug_log import agent_debug_log
from packages.voice_runtime.audio import AudioEnvelope, StatefulResampler, pcm_rms_s16le
from packages.voice_runtime.audio_audit import audio_audit_enabled
from packages.voice_runtime.audio_ring import AudioRingBuffer
from packages.voice_runtime.echo_ref_gate import (
    EchoVerdict,
    echo_ref_gate_enabled,
    lab_barge_in_enabled,
)
from packages.voice_runtime.forensic import ForensicTurnSnapshot, utc_now_iso
from packages.voice_runtime.lab_half_duplex import (
    lab_half_duplex_enabled,
    post_speech_pause_ms,
    uplink_preroll_ms,
)
from packages.voice_runtime.media_health import MediaHealth, MediaHealthTracker
from packages.voice_runtime.opening_cache import load_opening
from packages.voice_runtime.playback import PlaybackQueue
from packages.voice_runtime.profile import audio_settings, dialogue_timing_settings
from packages.voice_runtime.silero_vad import create_vad
from packages.voice_runtime.turn_fsm import ConversationPhase, TurnManager
from packages.voice_runtime.utterance_builder import UtteranceBuilder
from packages.voice_runtime.wait_state import DialogueTimingProfile, WaitState
from services.llm.http_provider import HttpLLMProvider
from services.providers.http_clients import get_shared_async_client
from services.stt.http_provider import HttpSTTProvider
from services.stt.normalize import normalize_transcript
from services.tts.http_provider import HttpTTSProvider

log = logging.getLogger("call_actor")

_SKIP_RENDER_INTENTS = frozenset(
    {
        "greeting",
        "opening_wellness",
        "identity_intro",
        "confirm_identity",
        "repeat_identity",
        "confirm_consent",
        "check_can_talk",
        "ack_wellness",
        "repair_repeat",
        "partial_unresolved_close",
    }
) | frozenset({f"check_{s}" for s in ("wellness", "mood", "sleep", "plans")}) | frozenset(
    {f"clarify_{s}" for s in ("wellness", "mood", "sleep", "plans")}
) | frozenset({f"repeat_{s}" for s in ("wellness", "mood", "sleep", "plans")})
_QUESTION_DELIVERY_INTENTS = frozenset(
    {
        "opening_wellness",
        "confirm_identity",
        "repeat_identity",
        "confirm_consent",
        "check_can_talk",
    }
)
_SENTENCE_END = re.compile(r"[.!?…]+(?:\s|$)")

EmitFn = Callable[[RuntimeEvent], Awaitable[None]]


@dataclass(frozen=True)
class MediaCallbacks:
    send_pcm: Callable[[bytes], Awaitable[None]]
    flush: Callable[[], Awaitable[None]]
    hangup: Callable[[], Awaitable[None]]
    emit: EmitFn
    prime_downlink: Callable[[], Awaitable[None]] | None = None
    finish: Callable[[], Awaitable[None]] | None = None


class ActorEventType(StrEnum):
    PCM = "pcm"
    STOP = "stop"


@dataclass
class ActorEvent:
    kind: ActorEventType
    pcm: bytes = b""
    sample_rate: int = 16000


@dataclass
class _TurnBudget:
    started_mono: float
    deadline: float


@dataclass
class _UtteranceOutcome:
    utterance_seq: int
    utterance_id: str
    ok: bool
    text: str = ""
    interp: object | None = None
    legacy_contract: object | None = None
    rich_turn: object | None = None
    asr_quality: AsrQuality = AsrQuality.GOOD
    error_stage: str | None = None
    error: str | None = None


@dataclass
class CallActorConfig:
    target_sample_rate: int = 16000
    stt_deadline_s: float = 12.0
    llm_deadline_s: float = 15.0
    tts_deadline_s: float = 20.0
    playback_buffer_ms: int = 60
    frame_ms: int = 20
    telephony_stream: bool = True
    # Lab Zoiper/softphone: hard mute during Vera (friend MVP). Default on —
    # always-listen + IMVERA_ECHO_REF_GATE is opt-in until live-stable.
    lab_half_duplex: bool = True
    post_speech_pause_ms: int = 100
    uplink_preroll_ms: int = 300
    # Drop uplink frames that match recently injected downlink PCM.
    echo_ref_gate: bool = False
    # Interrupt Vera on clear user speech during playback (lab; default off).
    lab_barge_in: bool = False


@dataclass
class CallActor:
    call_id: str
    family_id: str
    session: CallSession
    stt: HttpSTTProvider
    tts: TTSProvider
    llm: HttpLLMProvider
    media: MediaCallbacks
    config: CallActorConfig = field(default_factory=CallActorConfig)
    _queue: asyncio.Queue[ActorEvent] = field(default_factory=asyncio.Queue)
    _task: asyncio.Task | None = None
    _playback_task: asyncio.Task | None = None
    _policy_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _input_resampler: StatefulResampler | None = None
    _tts_resamplers: dict[str, StatefulResampler] = field(default_factory=dict)
    _vad: object | None = None
    _utterance_builder: UtteranceBuilder | None = None
    _collector: UtteranceBuilder | None = None
    _perception: PerceptionSession | None = None
    _raw_ring: AudioRingBuffer | None = None
    _playback: PlaybackQueue | None = None
    _active_generation: str | None = None
    _render_generation: str | None = None
    _tts_task: asyncio.Task | None = None
    _utterance_seq: int = 0
    _delivered_phrases: list[str] = field(default_factory=list)
    _stopped: bool = False
    _media_ready: bool = False
    _pending_open: SessionTurnResult | None = None
    _output_sample_rate: int = 16000
    _output_frame_bytes: int = 640
    _inflight_utterances: set[int] = field(default_factory=set)
    _last_applied_utterance_seq: int = 0
    _utterance_outcomes: dict[int, _UtteranceOutcome] = field(default_factory=dict)
    _utterance_budgets: dict[int, _TurnBudget] = field(default_factory=dict)
    _active_stage_budget: _TurnBudget | None = None
    _playback_turn_generation: str | None = None
    _transport_closed: bool = False
    _capture_lost: bool = False
    _active_llm_request_id: str | None = None
    _wait_task: asyncio.Task | None = None
    _wait_state: WaitState | None = None
    _engine_timer_task: asyncio.Task | None = None
    _engine_timer_id: str | None = None
    _engine_timer_revision: int | None = None
    _engine_timer_effect_id: str | None = None
    _control_epoch: int = 0
    _timing_profile: DialogueTimingProfile = field(
        default_factory=lambda: DialogueTimingProfile(**dialogue_timing_settings())
    )
    _monotonic: Callable[[], float] = field(default=time.monotonic, repr=False)
    _outbox_action_id: str | None = None
    _pending_answer_wait: tuple[str | None, str | None] | None = None
    _pending_mark_spoken_id: str | None = None
    _pending_speak_effect_id: str | None = None
    _pending_mark_render_gen: str | None = None
    _last_delivered_intent: str | None = None
    _tts_first_pcm_gens: set[str] = field(default_factory=set)
    _tts_slow_watch: asyncio.Task | None = None
    _hold_turn_finalize: bool = False
    _pending_end_call_effect: EndCallEffect | None = None
    _finalized_playback_gens: set[str] = field(default_factory=set)
    _finalize_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _uplink_total_bytes: int = 0
    _uplink_rms_peak: float = 0.0
    _listen_uplink_bytes: int = 0
    _listen_rms_peak: float = 0.0
    _listen_blocked_bytes: int = 0
    _debug_uplink_tick: int = 0
    _media_health: MediaHealthTracker = field(default_factory=MediaHealthTracker)
    _audio_echo_drop_logged: int = 0
    _forensic_bot_playout_end_ts: str | None = None
    _forensic_listen_open_ts: str | None = None
    _forensic_vad_start_ts: str | None = None
    _forensic_vad_end_ts: str | None = None
    _forensic_segment_echo_max: float = 0.0

    def _forensic_active(self) -> bool:
        return os.environ.get("IMVERA_FORENSIC", "0") in {"1", "true", "yes"}

    def _stt_dump_enabled(self) -> bool:
        if self._forensic_active():
            return True
        return os.environ.get("IMVERA_STT_DUMP", "0") in {"1", "true", "yes"}

    def _bump_forensic_echo_score(self, score: float) -> None:
        if score > self._forensic_segment_echo_max:
            self._forensic_segment_echo_max = score

    async def _emit_forensic_turn(
        self,
        *,
        utterance_id: str,
        stt_text: str,
        stt_rms: float,
        stt_duration_ms: int,
        stt_latency_ms: int,
        dump_path: str,
        delivered_slot: str,
        interpret_path: str,
        interpret_latency_ms: int,
        stt_request_ts: str,
        stt_result_ts: str,
    ) -> None:
        last_bot = self._delivered_phrases[-1] if self._delivered_phrases else ""
        snapshot = ForensicTurnSnapshot(
            utterance_id=utterance_id,
            bot_playout_end_ts=self._forensic_bot_playout_end_ts,
            listen_open_ts=self._forensic_listen_open_ts,
            vad_speech_start_ts=self._forensic_vad_start_ts,
            vad_speech_end_ts=self._forensic_vad_end_ts,
            stt_audio_start_ts=stt_request_ts,
            stt_audio_end_ts=stt_result_ts,
            stt_rms=stt_rms,
            stt_duration_ms=stt_duration_ms,
            stt_latency_ms=stt_latency_ms,
            last_bot_text=last_bot,
            stt_text=stt_text,
            echo_similarity=text_echo_similarity(stt_text, last_bot),
            echo_score_max=round(self._forensic_segment_echo_max, 3),
            delivered_slot=delivered_slot,
            interpret_path=interpret_path,
            interpret_latency_ms=interpret_latency_ms,
            dump_path=dump_path,
        )
        await self._emit_stage("forensic.turn", **snapshot.as_payload())
        self._forensic_vad_start_ts = None
        self._forensic_vad_end_ts = None
        self._forensic_segment_echo_max = 0.0

    def _active_builder(self) -> UtteranceBuilder | None:
        return self._utterance_builder or self._collector

    def _ensure_perception(self) -> PerceptionSession:
        if self._perception is None:
            self._perception = PerceptionSession(
                PerceptionConfig(
                    sample_rate=self.config.target_sample_rate,
                    echo_ref_gate=self.config.echo_ref_gate,
                    lab_half_duplex=self.config.lab_half_duplex,
                    lab_barge_in=self.config.lab_barge_in,
                    post_speech_pause_ms=self.config.post_speech_pause_ms,
                    uplink_preroll_ms=self.config.uplink_preroll_ms,
                )
            )
        return self._perception

    @property
    def _turn_manager(self) -> TurnManager:
        return self._ensure_perception().turn_manager

    @property
    def _playback_uplink_buf(self) -> bytearray:
        return self._ensure_perception()._uplink_preroll_buf

    @property
    def _playback_ref(self):
        perception = self._perception
        if perception is None:
            return None
        return perception.playback_ref

    @property
    def _listen_gated_until(self) -> float | None:
        perception = self._perception
        if perception is None:
            return None
        return perception._listen_gated_until

    @property
    def _blocked_preroll_pending(self) -> bytes:
        return self._ensure_perception().blocked_preroll_pending

    @_blocked_preroll_pending.setter
    def _blocked_preroll_pending(self, value: bytes) -> None:
        perception = self._ensure_perception()
        perception._blocked_preroll_pending = value

    async def _emit_stage(self, stage: str, **payload: object) -> None:
        started = self._active_stage_budget.started_mono if self._active_stage_budget else 0.0
        elapsed_ms = int((time.monotonic() - started) * 1000) if started else 0
        await self.media.emit(
            RuntimeEvent(
                self.call_id,
                RuntimeEventType.STAGE_TIMING,
                {"stage": stage, "elapsed_ms": elapsed_ms, **payload},
            )
        )

    async def _cancel_active_llm(self) -> None:
        rid = self._active_llm_request_id
        if not rid:
            return
        self._active_llm_request_id = None
        await self.llm.cancel_request(rid)

    @staticmethod
    def _split_complete_phrases(text: str) -> tuple[list[str], str]:
        phrases: list[str] = []
        rest = text
        while rest:
            match = _SENTENCE_END.search(rest)
            if not match:
                break
            phrase = rest[: match.end()].strip()
            rest = rest[match.end() :].lstrip()
            if phrase:
                phrases.append(phrase)
        return phrases, rest

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_wrapper())

    async def _run_wrapper(self) -> None:
        try:
            await self._run()
        except Exception:
            log.exception("CallActor crashed call_id=%s", self.call_id)
            raise

    async def stop(self) -> None:
        self._stopped = True
        await self._queue.put(ActorEvent(ActorEventType.STOP))
        if self._task:
            await self._task

    async def on_media_ready(
        self,
        output_sample_rate: int,
        output_frame_size: int,
        *,
        input_sample_rate: int | None = None,
    ) -> None:
        if input_sample_rate is not None:
            await self._ensure_input_chain(input_sample_rate)
        await self._ensure_output_chain(output_sample_rate, output_frame_size)
        self._media_ready = True
        if self._playback_task is None:
            self._playback_task = asyncio.create_task(self._playback_pump())
        if self.media.prime_downlink:
            await self.media.prime_downlink()
        if self._pending_open:
            await self._deliver_session_turn(self._pending_open)
            self._pending_open = None

    async def push_pcm(self, pcm: bytes, sample_rate: int) -> None:
        if self._stopped or self._transport_closed or self._capture_lost:
            return
        await self._queue.put(ActorEvent(ActorEventType.PCM, pcm=pcm, sample_rate=sample_rate))

    async def on_capture_lost(self) -> None:
        if self._stopped or self._transport_closed or self._capture_lost:
            return
        self._capture_lost = True
        await self.media.emit(
            RuntimeEvent(self.call_id, RuntimeEventType.CAPTURE_LOST, {})
        )
        self._transport_closed = True
        await self._interrupt_playback(flush=False)
        await self._finalize_disconnect()
        await self.media.hangup()

    async def _run(self) -> None:
        open_result = await asyncio.to_thread(self.session.start)
        await self.media.emit(
            RuntimeEvent(self.call_id, RuntimeEventType.CALL_STARTED, {})
        )
        if open_result.validated.allowed and open_result.validated.speech:
            self._pending_open = open_result
            if self._media_ready:
                await self._deliver_session_turn(open_result)
                self._pending_open = None

        while True:
            event = await self._queue.get()
            if event.kind == ActorEventType.STOP:
                await self._interrupt_playback(flush=False)
                await self._finalize_disconnect()
                await self.media.emit(
                    RuntimeEvent(self.call_id, RuntimeEventType.CALL_ENDED, {})
                )
                await self.media.emit(
                    RuntimeEvent(
                        self.call_id, RuntimeEventType.TRANSPORT_DISCONNECTED, {}
                    )
                )
                break
            if event.kind == ActorEventType.PCM:
                await self._on_pcm(event.pcm, event.sample_rate)

    async def _finalize_disconnect(self) -> None:
        if self.session.state.call_finalized:
            return
        if not self.session.state.final_action_done:
            self.session.state.final_action_done = True
            self.session.state.termination_reason = TerminationReason.DISCONNECTED
        await asyncio.to_thread(self.session.finalize_if_needed)

    async def _ensure_output_chain(
        self, output_sample_rate: int, output_frame_size: int
    ) -> None:
        if self._playback is not None:
            return
        self._output_sample_rate = output_sample_rate
        self._output_frame_bytes = output_frame_size
        self._playback = PlaybackQueue(
            self.call_id,
            buffer_limit_ms=self.config.playback_buffer_ms,
            sample_rate=output_sample_rate,
            frame_ms=self.config.frame_ms,
        )
        await self.media.emit(
            RuntimeEvent(
                self.call_id,
                RuntimeEventType.MEDIA_READY,
                {
                    "sample_rate": output_sample_rate,
                    "capture_sample_rate": self._input_resampler.source_rate
                    if self._input_resampler
                    else None,
                },
            )
        )

    async def _ensure_input_chain(self, capture_sample_rate: int) -> None:
        if (
            self._input_resampler is not None
            and self._input_resampler.source_rate == capture_sample_rate
        ):
            return
        self._input_resampler = StatefulResampler(
            capture_sample_rate, self.config.target_sample_rate
        )
        self._vad = create_vad(self.config.target_sample_rate)
        self._utterance_builder = UtteranceBuilder(self.config.target_sample_rate)
        self._collector = self._utterance_builder
        if self._raw_ring is None:
            self._raw_ring = AudioRingBuffer(
                self.config.target_sample_rate,
                max_ms=max(4000, self.config.uplink_preroll_ms),
            )

    def _flush_pcm_queue(self) -> None:
        """Drop pending PCM from queue into preroll; keep STOP for hangup."""
        kept: list[ActorEvent] = []
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item.kind == ActorEventType.STOP:
                kept.append(item)
            elif item.kind == ActorEventType.PCM and item.pcm:
                self._append_uplink_preroll(item.pcm)
        for item in kept:
            self._queue.put_nowait(item)

    def _should_drop_echo_for_vad(self, pcm: bytes, *, playback_active: bool) -> bool:
        """Gate Vera echo from VAD; never deletes raw capture."""
        if self._playback_ref is None:
            return False
        classification = self._playback_ref.classify(pcm, playback_active=playback_active)
        if classification.verdict == EchoVerdict.ECHO:
            return True
        if classification.verdict == EchoVerdict.UNCERTAIN and playback_active:
            return True
        return False

    def _uplink_speech_active(self) -> bool:
        """True when VAD/collector believe user speech is in progress."""
        if self._collector is not None and getattr(self._collector, "collecting", False):
            return True
        if self._vad is not None and getattr(self._vad, "in_speech", False):
            return True
        return False

    async def _finalize_active_speech_before_listen_reset(self) -> bool:
        """Flush in-progress segment before VAD reset on listen.enabled (sip-72d8)."""
        if self._collector is None:
            return False
        finalize = getattr(self._collector, "force_finalize", None)
        if not callable(finalize):
            return False
        segment = finalize()
        if not segment:
            return False
        if not self._turn_manager.should_emit_utterance():
            await self._emit_stage(
                "turn.discarded",
                reason="listen_reset",
                pcm_bytes=len(segment.pcm if hasattr(segment, "pcm") else segment),
            )
            return True
        pcm_bytes = segment.pcm if hasattr(segment, "pcm") else segment
        await self.media.emit(
            RuntimeEvent(self.call_id, RuntimeEventType.SPEECH_ENDED, {})
        )
        async with self._policy_lock:
            utterance_seq = self._utterance_seq + 1
            self._utterance_seq = utterance_seq
        self._inflight_utterances.add(utterance_seq)
        self._turn_manager.on_stt_submitted()
        asyncio.create_task(self._handle_utterance(pcm_bytes, utterance_seq))
        await self._emit_stage(
            "vad.reset_on_listen",
            had_active_speech=True,
            segment_bytes=len(pcm_bytes),
        )
        return True

    def _should_suppress_speech_start_during_playback(self, pcm: bytes) -> bool:
        """Block false speech.started from Vera echo during TTS."""
        if not self._active_generation:
            return False
        if self.config.lab_barge_in:
            return False
        return self._ensure_perception().should_suppress_speech_start(
            pcm, playback_active=True
        )

    def _reset_uplink_endpointing(self) -> None:
        """Clear utterance assembly state after assistant playback — VAD stays hot."""
        if self._utterance_builder is not None:
            self._utterance_builder.reset_pending()

    def _push_echo_downlink(self, pcm_s16le: bytes, sample_rate: int) -> None:
        """Feed injected downlink into playback reference at uplink/VAD sample rate."""
        if not self._effective_echo_ref_gate() or not pcm_s16le:
            return
        target = int(self.config.target_sample_rate)
        src = int(sample_rate) or target
        if src == target:
            self._ensure_perception().push_downlink(pcm_s16le)
            return
        key = f"echo_ref:{src}->{target}"
        resampler = self._tts_resamplers.get(key)
        if resampler is None:
            resampler = StatefulResampler(src, target)
            self._tts_resamplers[key] = resampler
        converted = resampler.process(pcm_s16le)
        if converted:
            self._ensure_perception().push_downlink(converted)

    @staticmethod
    def _normalize_speech_text(text: str) -> str:
        cleaned = re.sub(r"[^\w\s]", " ", text.lower())
        return " ".join(cleaned.split())

    def _assistant_echo_candidates(self) -> list[str]:
        """Phrases Vera already said or is saying — used to drop acoustic echo STT."""
        candidates = list(self._delivered_phrases)
        if self._playback and self._playback._ledger:
            spoken = self._playback._ledger.canonical_text
            if spoken and (not candidates or candidates[-1] != spoken):
                candidates.append(spoken)
        pending = self.session.state.pending_question
        if pending:
            candidates.append(pending)
        return candidates

    # Elder wellness/mood answers — never treat as Vera echo (sip deaf reports).
    _SLOT_ANSWER_ALLOWLIST = frozenset(
        {
            "хорошо",
            "нормально",
            "плохо",
            "не очень",
            "отлично",
            "так себе",
            "чувствую себя хорошо",
            "чувствую себя плохо",
            "себя хорошо",
            "себя плохо",
            "хорошее",
            "плохое",
            "да",
            "нет",
            "какое",
            "какая",
            "какой",
            "какие",
            "что",
            "как",
        }
    )

    def _is_assistant_echo(self, text: str) -> bool:
        return self._ensure_perception().is_assistant_text_echo(
            text,
            self._assistant_echo_candidates(),
            allowlist=self._SLOT_ANSWER_ALLOWLIST,
        )

    def _remember_assistant_phrase(self, text: str) -> None:
        spoken = (text or "").strip()
        if not spoken:
            return
        if not self._delivered_phrases or self._delivered_phrases[-1] != spoken:
            self._delivered_phrases.append(spoken)

    def _effective_echo_ref_gate(self) -> bool:
        return bool(self.config.echo_ref_gate)

    def _ensure_playback_ref(self) -> None:
        self._ensure_perception().ensure_playback_ref()

    def _ensure_echo_ref(self) -> None:
        """Compat alias for tests and legacy call sites."""
        self._ensure_playback_ref()

    @property
    def _echo_ref(self) -> object | None:
        perception = self._perception
        if perception is None or perception.playback_ref is None:
            return None
        return perception.playback_ref._ref

    def _on_bot_playback_started(self) -> None:
        intent = self._last_delivered_intent or ""
        self._ensure_perception().on_playback_started(intent)

    async def _await_echo_tail(self) -> None:
        while True:
            now = self._monotonic()
            self._turn_manager.tick(now)
            remaining = self._turn_manager.echo_tail_remaining_s(now)
            if remaining <= 0:
                break
            await asyncio.sleep(min(remaining, 0.05))

    def _uplink_listen_blocked(self) -> bool:
        """Hard mute only in classic half-duplex mode (friend MVP)."""
        return self._ensure_perception().uplink_listen_blocked(
            playback_active=bool(self._active_generation),
            now_mono=self._monotonic(),
        )

    def _force_listen_enabled(self) -> None:
        """Unmute uplink immediately — post-speech pause must not stick forever."""
        self._ensure_perception().force_listen_enabled()

    def _arm_post_speech_pause(self) -> None:
        """After playback.completed: keep mic muted for a short quiet window."""
        self._ensure_perception().arm_post_speech_pause(self._monotonic())

    async def _await_post_speech_pause(self) -> None:
        """Block until post-speech pause elapses; always clear gate afterward."""
        perception = self._ensure_perception()
        until = perception._listen_gated_until
        if until is None:
            return
        try:
            while True:
                remaining = until - self._monotonic()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(remaining, 0.05))
        finally:
            self._force_listen_enabled()

    def _reset_listen_uplink_stats(self) -> None:
        self._listen_uplink_bytes = 0
        self._listen_rms_peak = 0.0
        self._listen_blocked_bytes = 0

    def _track_uplink_pcm(self, pcm: bytes, *, fed_to_vad: bool) -> None:
        nbytes = len(pcm)
        if nbytes <= 0:
            return
        self._uplink_total_bytes += nbytes
        rms = pcm_rms_s16le(pcm)
        if rms > self._uplink_rms_peak:
            self._uplink_rms_peak = rms
        if fed_to_vad:
            self._listen_uplink_bytes += nbytes
            if rms > self._listen_rms_peak:
                self._listen_rms_peak = rms
        else:
            self._listen_blocked_bytes += nbytes

    async def _emit_uplink_summary(self, reason: str) -> None:
        await self._emit_stage(
            "uplink.summary",
            reason=reason,
            listen_uplink_bytes=self._listen_uplink_bytes,
            listen_rms_peak=round(self._listen_rms_peak, 1),
            listen_blocked_bytes=self._listen_blocked_bytes,
            uplink_total_bytes=self._uplink_total_bytes,
            uplink_rms_peak=round(self._uplink_rms_peak, 1),
            capture_lost=self._capture_lost,
        )

    def _append_uplink_preroll(self, pcm: bytes) -> None:
        """Ring-buffer uplink dropped during half-duplex mute for replay on listen."""
        self._ensure_perception()._append_preroll(pcm)

    async def _process_uplink_vad_frame(
        self, pcm: bytes, *, playback_active: bool, fed_to_vad: bool = True
    ) -> None:
        if fed_to_vad:
            self._track_uplink_pcm(pcm, fed_to_vad=True)
        started, ended = self._vad.feed(pcm)  # type: ignore[union-attr]
        speech_active = bool(getattr(self._vad, "in_speech", False))
        if started and self._should_suppress_speech_start_during_playback(pcm):
            started = False
        if started and self._blocked_preroll_pending:
            builder = self._active_builder()
            if builder is not None:
                builder.seed_external_preroll(self._blocked_preroll_pending)
            self._ensure_perception().consume_blocked_preroll()
        if started:
            self._forensic_vad_start_ts = utc_now_iso()
            self._forensic_segment_echo_max = 0.0
            self._turn_manager.on_vad_speech_started(self._monotonic())
            if self.config.lab_barge_in and playback_active:
                self._turn_manager.note_barge_in_candidate(self._monotonic())
            await self._emit_stage(
                "audio.speech_started",
                playback_active=playback_active,
                intent=self._last_delivered_intent or "",
                rms=round(pcm_rms_s16le(pcm), 1),
                turn_phase=str(self._turn_manager.phase),
            )
            # region agent log
            agent_debug_log(
                "D",
                "call_actor.py:_process_uplink_vad_frame",
                "speech_started",
                {
                    "call_id": self.call_id,
                    "playback_active": playback_active,
                    "intent": self._last_delivered_intent or "",
                    "rms": round(pcm_rms_s16le(pcm), 1),
                    "turn_phase": str(self._turn_manager.phase),
                },
            )
            # endregion
            self._pause_answer_wait()
            if self.session.uses_dialogue_engine():
                await self._cancel_engine_timer_on_speech_start()
            await self.media.emit(
                RuntimeEvent(self.call_id, RuntimeEventType.SPEECH_STARTED, {})
            )
            if playback_active and self.config.lab_barge_in:
                gen = self._active_generation
                self._turn_manager.confirm_barge_in()
                await self._interrupt_playback(flush=True)
                await self._emit_stage(
                    "bargein_detected",
                    generation_id=gen,
                    echo_ref_gate=True,
                )
        if ended:
            self._turn_manager.on_vad_speech_ended()
        builder = self._active_builder()
        built = None
        if builder is not None:
            try:
                built = builder.on_frame(
                    pcm,
                    speech_started=started,
                    speech_ended=ended,
                    speech_active=speech_active,
                )
            except TypeError:
                built = builder.on_frame(pcm, started, ended)  # type: ignore[misc]
        if built:
            if isinstance(built, bytes):
                pcm_out = built
                duration_ms = int(len(pcm_out) / max(2, self.config.target_sample_rate) * 1000)
                segment_rms = pcm_rms_s16le(pcm_out)
                silence_tail_ms = 0
            else:
                pcm_out = built.pcm
                duration_ms = built.duration_ms
                segment_rms = built.segment_rms
                silence_tail_ms = built.silence_tail_ms
            self._forensic_vad_end_ts = utc_now_iso()
            await self._emit_stage(
                "audio.speech_ended",
                pcm_bytes=len(pcm_out),
                duration_ms=duration_ms,
                segment_rms=round(segment_rms, 1),
                playback_active=playback_active,
                silence_tail_ms=silence_tail_ms,
                turn_phase=str(self._turn_manager.phase),
            )
            if not self._turn_manager.should_emit_utterance():
                await self._emit_stage(
                    "turn.discarded",
                    reason=str(self._turn_manager.phase),
                    pcm_bytes=len(pcm_out),
                    duration_ms=duration_ms,
                )
                await self.media.emit(
                    RuntimeEvent(self.call_id, RuntimeEventType.SPEECH_ENDED, {})
                )
                return
            await self.media.emit(
                RuntimeEvent(self.call_id, RuntimeEventType.SPEECH_ENDED, {})
            )
            async with self._policy_lock:
                utterance_seq = self._utterance_seq + 1
                self._utterance_seq = utterance_seq
            self._inflight_utterances.add(utterance_seq)
            self._turn_manager.on_stt_submitted()
            asyncio.create_task(self._handle_utterance(pcm_out, utterance_seq))

    async def _replay_uplink_preroll(self, preroll: bytes) -> None:
        """Feed buffered user speech into fresh VAD after half-duplex unmute.

        Skip frames that still match downlink reference — preroll often contains
        Vera echo captured during mute (sip-f21993a04f: false speech + echo_discard).
        """
        assert self._vad and self._collector
        if not preroll:
            return
        frame_bytes = max(2, self.config.target_sample_rate * 2 * self.config.frame_ms // 1000)
        for offset in range(0, len(preroll), frame_bytes):
            chunk = preroll[offset : offset + frame_bytes]
            if len(chunk) < 2:
                continue
            if self._playback_ref is not None:
                classification = self._playback_ref.classify(chunk, playback_active=False)
                if classification.verdict == EchoVerdict.ECHO:
                    continue
            await self._process_uplink_vad_frame(chunk, playback_active=False)

    async def _enable_listen_after_playback(self) -> None:
        """Echo tail → listen window. Raw capture always preserved; VAD stays hot."""
        self._ensure_perception().on_playback_completed(self._monotonic())
        try:
            await self._await_post_speech_pause()
            await self._await_echo_tail()
        finally:
            self._force_listen_enabled()
            self._flush_pcm_queue()
            had_active = await self._finalize_active_speech_before_listen_reset()
            if not had_active:
                await self._emit_stage("vad.reset_on_listen", had_active_speech=False)
            self._reset_uplink_endpointing()
            self._reset_listen_uplink_stats()
            preroll_bytes = self._ensure_perception().on_listen_enabled()
            self._forensic_listen_open_ts = utc_now_iso()
            await self._emit_stage(
                "listen.enabled",
                pause_ms=int(self.config.post_speech_pause_ms),
                lab_half_duplex=bool(self.config.lab_half_duplex),
                echo_ref_gate=bool(self.config.echo_ref_gate),
                effective_echo_ref_gate=bool(self._effective_echo_ref_gate()),
                turn_phase=str(self._turn_manager.phase),
                turn_policy=str(self._turn_manager.policy.kind),
                preroll_bytes=preroll_bytes,
            )
            # region agent log
            agent_debug_log(
                "B",
                "call_actor.py:_enable_listen_after_playback",
                "listen_enabled",
                {
                    "call_id": self.call_id,
                    "intent": self._last_delivered_intent or "",
                    "preroll_bytes": preroll_bytes,
                    "lab_half_duplex": bool(self.config.lab_half_duplex),
                    "turn_phase": str(self._turn_manager.phase),
                },
            )
            # endregion
            # Keep downlink reference for acoustic echo gate during the user turn.
            # Clearing here made Zoiper loopback invisible to PlaybackReference (sip-f21993a).

    async def _feed_uplink_pcm(self, pcm: bytes) -> None:
        assert self._vad and self._collector
        if self._raw_ring is not None:
            self._raw_ring.push(pcm)
        now = self._monotonic()
        if self._active_generation and self._turn_manager.phase not in {
            ConversationPhase.BOT_SPEAKING,
            ConversationPhase.BARGE_IN_CANDIDATE,
            ConversationPhase.USER_SPEAKING,
        }:
            self._on_bot_playback_started()
        playback_active = bool(self._active_generation)
        decision = self._ensure_perception().process_uplink(
            pcm,
            playback_active=playback_active,
            now_mono=now,
        )
        blocked = decision.blocked
        buffer_only = decision.buffer_only
        self._debug_uplink_tick += 1
        tick = self._debug_uplink_tick
        if audio_audit_enabled() and (
            tick in {1, 50, 200, 500} or tick % 500 == 0
        ):
            await self._emit_stage(
                "audio.uplink_tick",
                tick=tick,
                blocked=blocked or buffer_only,
                rms=round(pcm_rms_s16le(pcm), 1),
                playback_active=playback_active,
                intent=self._last_delivered_intent or "",
                turn_phase=str(self._turn_manager.phase),
            )
        if tick in {1, 50, 200, 500} or tick % 1000 == 0:
            agent_debug_log(
                "B",
                "call_actor.py:_feed_uplink_pcm",
                "uplink_tick",
                {
                    "call_id": self.call_id,
                    "tick": self._debug_uplink_tick,
                    "blocked": blocked or buffer_only,
                    "turn_phase": str(self._turn_manager.phase),
                    "active_gen": bool(self._active_generation),
                    "intent": self._last_delivered_intent or "",
                    "rms": round(pcm_rms_s16le(pcm), 1),
                    "pcm_len": len(pcm),
                },
            )
        if not decision.feed_vad:
            self._track_uplink_pcm(pcm, fed_to_vad=False)
            if decision.echo_verdict is not None:
                self._audio_echo_drop_logged += 1
                self._bump_forensic_echo_score(decision.echo_score)
                if self._audio_echo_drop_logged <= 30:
                    await self._emit_stage(
                        "audio.echo_classified",
                        classification=str(decision.echo_verdict),
                        score=round(decision.echo_score, 3),
                        playback_active=playback_active,
                        rms=round(pcm_rms_s16le(pcm), 1),
                    )
                if self._debug_uplink_tick in {1, 50, 200}:
                    agent_debug_log(
                        "C",
                        "call_actor.py:_feed_uplink_pcm",
                        "echo_classified",
                        {
                            "call_id": self.call_id,
                            "playback_active": playback_active,
                            "verdict": str(decision.echo_verdict),
                            "score": decision.echo_score,
                            "rms": round(pcm_rms_s16le(pcm), 1),
                        },
                    )
            return
        await self._process_uplink_vad_frame(pcm, playback_active=playback_active)

    def _tts_resampler(self, generation_id: str, source_rate: int) -> StatefulResampler:
        key = f"{generation_id}:{source_rate}"
        if key not in self._tts_resamplers:
            self._tts_resamplers[key] = StatefulResampler(source_rate, self._output_sample_rate)
        return self._tts_resamplers[key]

    def _resample_tts_chunk(self, generation_id: str, pcm: bytes, source_rate: int) -> bytes:
        if source_rate == self._output_sample_rate:
            return pcm
        return self._tts_resampler(generation_id, source_rate).process(pcm)

    async def _on_pcm(self, pcm_s16le: bytes, sample_rate: int) -> None:
        if self._stopped or not self._media_ready or self._transport_closed:
            return
        await self._ensure_input_chain(sample_rate)
        assert self._input_resampler and self._vad and self._collector
        pcm = self._input_resampler.process(pcm_s16le)
        if not pcm:
            return
        self._media_health.note_actor_frame(
            len(pcm), pcm_rms_s16le(pcm), now=self._monotonic()
        )
        await self._feed_uplink_pcm(pcm)

    def note_rtp_statistics(
        self,
        *,
        rxcount: int,
        txcount: int,
        rxjitter: float = 0.0,
        rx_packet_loss: float = 0.0,
    ) -> None:
        now = self._monotonic()
        self._media_health.note_rtp_rx(rxcount, now=now)
        self._media_health.note_rtp_tx(txcount)
        self._media_health.note_rtp_quality(jitter=rxjitter, loss=rx_packet_loss)

    def note_capture_ingress(self, nbytes: int, rms: float) -> None:
        self._media_health.note_capture_frame(nbytes, rms, now=self._monotonic())

    async def _emit_media_pipeline_summary(self, reason: str) -> None:
        health = self._media_health.evaluate(now=self._monotonic())
        await self._emit_stage(
            "media.pipeline",
            reason=reason,
            health=str(health),
            **self._media_health.counters.to_trace_dict(),
        )

    async def _submit_utterance_outcome(self, outcome: _UtteranceOutcome) -> None:
        self._utterance_outcomes[outcome.utterance_seq] = outcome
        await self._drain_utterance_outcomes()

    async def _drain_utterance_outcomes(self) -> None:
        deliver_results: list[SessionTurnResult] = []
        failed_events: list[RuntimeEvent] = []
        async with self._policy_lock:
            while True:
                next_seq = self._last_applied_utterance_seq + 1
                outcome = self._utterance_outcomes.get(next_seq)
                if outcome is None:
                    break
                self._utterance_outcomes.pop(next_seq, None)
                self._inflight_utterances.discard(next_seq)
                self._last_applied_utterance_seq = next_seq
                if self._stopped or self._transport_closed:
                    continue
                if not outcome.ok:
                    if outcome.error and not self._stopped:
                        failed_events.append(
                            RuntimeEvent(
                                self.call_id,
                                RuntimeEventType.INTERPRETATION_FAILED,
                                {
                                    "error": outcome.error,
                                    "stage": outcome.error_stage or "unknown",
                                },
                            )
                        )
                    continue
                if not outcome.text or outcome.interp is None or outcome.legacy_contract is None:
                    continue
                result = await asyncio.to_thread(
                    self.session.handle_user_text,
                    outcome.text,
                    interp=outcome.interp,
                    contract=outcome.legacy_contract,
                    utterance_id=outcome.utterance_id,
                    asr_quality=outcome.asr_quality,
                    rich_turn=outcome.rich_turn,
                )
                deliver_results.append(result)
                self._turn_manager.on_turn_applied()
        for event in failed_events:
            await self.media.emit(event)
        for result in deliver_results:
            await self._enqueue_turn_delivery(result)
        await self._flush_deferred_engine_turn()

    def _bump_control_epoch(self) -> int:
        self._control_epoch += 1
        return self._control_epoch

    async def _cancel_engine_timer_on_speech_start(self) -> None:
        timer_id = self._engine_timer_id
        if not timer_id:
            return
        await self._cancel_engine_timer()
        engine = self.session._engine
        if engine is not None:
            engine.outbox.cancel_timer_by_id(timer_id)

    async def _cancel_engine_timer(self) -> None:
        if self._engine_timer_task and not self._engine_timer_task.done():
            self._engine_timer_task.cancel()
            try:
                await self._engine_timer_task
            except asyncio.CancelledError:
                pass
        self._engine_timer_task = None
        self._engine_timer_id = None
        self._engine_timer_revision = None
        self._engine_timer_effect_id = None

    async def _schedule_engine_timer(self, timer: TimerEffect) -> None:
        await self._cancel_engine_timer()
        self._engine_timer_id = timer.timer_id
        self._engine_timer_revision = timer.revision
        self._engine_timer_effect_id = timer.effect_id
        wait_ms = timer.wait_ms
        timer_id = timer.timer_id
        revision = timer.revision

        async def _sleep_then_fire() -> None:
            try:
                await asyncio.sleep(wait_ms / 1000.0)
            except asyncio.CancelledError:
                return
            await self._on_engine_timer_expired(timer_id, revision)

        self._engine_timer_task = asyncio.create_task(_sleep_then_fire())

    async def _on_engine_timer_expired(self, timer_id: str, revision: int) -> None:
        self._engine_timer_task = None
        if self._stopped or self._transport_closed:
            return
        if revision != self._engine_timer_revision:
            return
        if self._inflight_utterances:
            return
        if not self.session.uses_dialogue_engine():
            return
        expired = await asyncio.to_thread(self.session.handle_wait_expired, timer_id)
        await self._post_apply_turn(expired)

    async def _cancel_wait_timer(self) -> None:
        if self._wait_task and not self._wait_task.done():
            self._wait_task.cancel()
            try:
                await self._wait_task
            except asyncio.CancelledError:
                pass
        self._wait_task = None
        self._wait_state = None

    def _start_answer_wait(
        self,
        *,
        goal_id: str | None,
        question_id: str | None,
    ) -> None:
        if self._wait_task and not self._wait_task.done():
            self._wait_task.cancel()
        self._wait_task = None
        self._wait_state = WaitState.start_answer_wait(
            goal_id=goal_id,
            question_id=question_id,
            control_epoch=self._control_epoch,
            profile=self._timing_profile,
            now_mono=self._monotonic(),
        )
        self._media_health.set_waiting_for_answer(True, now=self._monotonic())
        self._schedule_wait_timer()

    def _pause_answer_wait(self) -> None:
        if self._wait_state is None:
            return
        self._wait_state.pause_for_speech(now_mono=self._monotonic())
        if self._wait_task and not self._wait_task.done():
            self._wait_task.cancel()

    def _resume_answer_wait_if_paused(self) -> None:
        if self._wait_state is None or not self._wait_state.speech_paused:
            return
        self._wait_state.resume_after_speech()
        self._schedule_wait_timer()

    def _schedule_wait_timer(self) -> None:
        if self._wait_state is None:
            return
        if self._wait_task and not self._wait_task.done():
            self._wait_task.cancel()
        wait_id = self._wait_state.wait_id
        epoch = self._wait_state.control_epoch
        remaining_ms = self._wait_state.remaining_ms(self._monotonic())
        if remaining_ms <= 0:
            self._wait_task = asyncio.create_task(self._on_wait_deadline(wait_id, epoch))
            return

        async def _sleep_then_fire() -> None:
            try:
                await asyncio.sleep(remaining_ms / 1000.0)
            except asyncio.CancelledError:
                return
            await self._on_wait_deadline(wait_id, epoch)

        self._wait_task = asyncio.create_task(_sleep_then_fire())

    async def _on_wait_deadline(self, wait_id: str, control_epoch: int) -> None:
        self._wait_task = None
        if self._stopped or self._transport_closed:
            return
        if control_epoch != self._control_epoch:
            return
        state = self._wait_state
        if state is None or state.wait_id != wait_id:
            return
        if not state.should_fire(self._monotonic()):
            self._schedule_wait_timer()
            return
        if self._inflight_utterances:
            self._schedule_wait_timer()
            return
        self._wait_state = None
        health = self._media_health.evaluate(now=self._monotonic())
        await self._emit_media_pipeline_summary("answer_wait_check")
        if health != MediaHealth.HEALTHY:
            self._media_health.set_waiting_for_answer(False, now=self._monotonic())
            await self._emit_stage(
                "media.stalled",
                health=str(health),
                reason="answer_wait_blocked",
            )
            await self._emit_uplink_summary("media_stalled")
            return
        self._media_health.set_waiting_for_answer(False, now=self._monotonic())
        await self._emit_uplink_summary("answer_wait_timeout")
        expired = await asyncio.to_thread(self.session.handle_wait_expired, wait_id)
        await self._post_apply_turn(expired)

    async def _handle_backchannel_continuation(self, result: SessionTurnResult) -> None:
        goal_id = result.proposal.wait_goal_id
        if self._wait_state is None:
            slot = self.session.state.pending_slot
            goal = self.session.state.get_goal(slot) if slot else None
            self._start_answer_wait(
                goal_id=goal_id or (goal.goal_id if goal else None),
                question_id=goal.last_question_id if goal else None,
            )
        else:
            self._wait_state.resume_after_speech()
            self._wait_state.apply_backchannel_extra(
                self._timing_profile, now_mono=self._monotonic()
            )
            self._wait_state.rebind_control(self._control_epoch)
        self._schedule_wait_timer()

    def _start_pause_wait(self) -> None:
        if self._wait_task and not self._wait_task.done():
            self._wait_task.cancel()
        self._wait_task = None
        self._wait_state = WaitState.start_pause_wait(
            control_epoch=self._control_epoch,
            profile=self._timing_profile,
            now_mono=self._monotonic(),
        )
        self._schedule_wait_timer()

    async def _finalize_outbox_action(
        self,
        *,
        sent_samples: int,
        outcome: str,
    ) -> None:
        action_id = self._outbox_action_id
        if not action_id:
            return
        record = await asyncio.to_thread(
            self.session.transitions.get_outbox_record,
            self.session.state.call_id,
            action_id,
        )
        if record is not None and record.status == ActionOutboxStatus.PENDING:
            await asyncio.to_thread(
                self.session.transitions.mark_outbox_dispatching,
                self.session.state,
                action_id,
            )
        if outcome == "success" and sent_samples > 0:
            await asyncio.to_thread(
                self.session.transitions.mark_outbox_transport_complete,
                self.session.state,
                action_id,
                sent_samples=sent_samples,
            )
        elif sent_samples > 0:
            await asyncio.to_thread(
                self.session.transitions.mark_outbox_delivery_unknown,
                self.session.state,
                action_id,
                sent_samples=sent_samples,
            )
        else:
            await asyncio.to_thread(
                self.session.transitions.mark_outbox_cancelled,
                self.session.state,
                action_id,
            )
            await asyncio.to_thread(
                Planner.release_question_attempt,
                self.session.state,
                action_id,
            )
        self._outbox_action_id = None

    async def _post_apply_turn(self, result: SessionTurnResult) -> None:
        if self._stopped or self._transport_closed:
            return
        if not result.persist_ok:
            await self.media.emit(
                RuntimeEvent(
                    self.call_id,
                    RuntimeEventType.PERSISTENCE_FAILED,
                    {"error": result.persist_error},
                )
            )
            return
        await self.media.emit(
            RuntimeEvent(self.call_id, RuntimeEventType.PERSISTENCE_COMMITTED, {})
        )
        if result.from_engine:
            await self._emit_stage(
                "dialogue.engine_decision",
                intent=result.proposal.intent,
                skip_planner=True,
                turn_id=result.proposal.turn_id,
            )
        else:
            await self._emit_stage(
                "dialogue.planner_decision",
                intent=result.proposal.intent,
                skip_planner=False,
                turn_id=result.proposal.turn_id,
            )
        if (
            result.end_call_effect is not None
            and result.speak_effect is None
            and result.timer_effect is None
        ):
            await self._schedule_end_call_effect(result.end_call_effect)
            return
        await self._enqueue_turn_delivery(result)

    async def _enqueue_turn_delivery(self, result: SessionTurnResult) -> None:
        if self._stopped or self._transport_closed:
            return
        if self._inflight_utterances and result.speak_effect is not None:
            await self._emit_stage(
                "delivery.deferred",
                effect_id=result.speak_effect.effect_id,
                revision=result.speak_effect.revision,
                intent=result.proposal.intent,
            )
            await asyncio.to_thread(self.session.defer_engine_turn, result)
            return
        if result.speak_effect is not None:
            valid = await asyncio.to_thread(
                self.session.is_engine_speak_valid, result.speak_effect
            )
            if not valid:
                await self._on_stale_speak_effect(
                    result.speak_effect,
                    intent=result.proposal.intent,
                    reason="enqueue",
                )
                return
        await self._deliver_session_turn(result)

    async def _on_stale_speak_effect(
        self,
        effect: SpeakEffect,
        *,
        intent: str,
        reason: str,
    ) -> None:
        await self._emit_stage(
            "stale_speak_effect_dropped",
            effect_id=effect.effect_id,
            revision=effect.revision,
            engine_revision=self.session._engine.revision
            if self.session._engine
            else None,
            intent=intent,
            reason=reason,
        )
        replacement = await asyncio.to_thread(
            self.session.handle_stale_speak_effect, effect
        )
        if replacement is not None:
            await self._post_apply_turn(replacement)

    async def _flush_deferred_engine_turn(self) -> None:
        if self._inflight_utterances or self._stopped or self._transport_closed:
            return
        result = await asyncio.to_thread(self.session.flush_deferred_engine_turn)
        if result is None:
            return
        if result.speak_effect is not None:
            valid = await asyncio.to_thread(
                self.session.is_engine_speak_valid, result.speak_effect
            )
            if not valid:
                await self._on_stale_speak_effect(
                    result.speak_effect,
                    intent=result.proposal.intent,
                    reason="deferred_flush",
                )
                return
        await self._deliver_session_turn(result)

    def _stt_dump_pcm(self, pcm: bytes, utterance_id: str) -> str | None:
        """Optional WAV dump for offline STT benchmark — IMVERA_STT_DUMP or IMVERA_FORENSIC."""
        if not self._stt_dump_enabled():
            return None
        dump_dir = Path(__file__).resolve().parents[2] / ".run" / "stt_dumps"
        dump_dir.mkdir(parents=True, exist_ok=True)
        path = dump_dir / f"{self.call_id}_{utterance_id}.wav"
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.config.target_sample_rate)
            wf.writeframes(pcm)
        return str(path)

    async def _handle_utterance(self, pcm: bytes, utterance_seq: int) -> None:
        try:
            await self._handle_utterance_inner(pcm, utterance_seq)
        finally:
            await self._flush_deferred_engine_turn()

    async def _handle_utterance_inner(self, pcm: bytes, utterance_seq: int) -> None:
        if self.session.uses_dialogue_engine():
            await self._cancel_engine_timer()
        if self._stopped or self._transport_closed:
            self._inflight_utterances.discard(utterance_seq)
            return
        utterance_id = f"u-{utterance_seq}"
        turn_id = self.session.turn_id + 1
        budget = _TurnBudget(
            started_mono=time.monotonic(),
            deadline=time.monotonic()
            + self.config.stt_deadline_s
            + self.config.llm_deadline_s,
        )
        self._utterance_budgets[utterance_seq] = budget
        self._active_stage_budget = budget
        sr = self.config.target_sample_rate
        duration_ms = int(len(pcm) / max(2, sr) * 1000) if pcm else 0
        pcm_rms = round(pcm_rms_s16le(pcm), 1)
        dump_path = self._stt_dump_pcm(pcm, utterance_id)
        stt_request_ts = utc_now_iso()
        self._media_health.note_stt_input()
        await self._emit_stage(
            "stt.request",
            utterance_id=utterance_id,
            turn_id=turn_id,
            pcm_bytes=len(pcm),
            duration_ms=duration_ms,
            pcm_rms=pcm_rms,
            dump_path=dump_path or "",
            pending_slot=self.session.state.pending_slot or "",
        )
        await self._emit_stage("utterance.start", utterance_id=utterance_id, turn_id=turn_id)
        # region agent log
        agent_debug_log(
            "E",
            "call_actor.py:_handle_utterance",
            "stt_invoke",
            {
                "call_id": self.call_id,
                "utterance_id": utterance_id,
                "pcm_bytes": len(pcm),
            },
        )
        # endregion
        try:
            try:
                stt_started = time.monotonic()
                stt_result = await self.stt.transcribe_final(
                    pcm,
                    self.config.target_sample_rate,
                    call_id=self.call_id,
                    turn_id=turn_id,
                    deadline=budget.deadline,
                    utterance_id=utterance_id,
                )
                stt_elapsed_ms = int((time.monotonic() - stt_started) * 1000)
            except Exception as exc:
                await self._submit_utterance_outcome(
                    _UtteranceOutcome(
                        utterance_seq=utterance_seq,
                        utterance_id=utterance_id,
                        ok=False,
                        error_stage="stt",
                        error=str(exc),
                    )
                )
                return
            if self._stopped or self._transport_closed:
                self._inflight_utterances.discard(utterance_seq)
                return

            text = normalize_transcript((stt_result.text or "").strip())
            raw_text = (
                getattr(stt_result, "raw_text", None) or stt_result.text or ""
            ).strip()
            stt_result_ts = utc_now_iso()
            await self._emit_stage(
                "stt.result",
                utterance_id=utterance_id,
                raw_text=raw_text,
                text=text,
                normalized_changed=raw_text != text,
                asr_quality=str(stt_result.asr_quality),
                duration_ms=getattr(stt_result, "duration_ms", None) or duration_ms,
                pcm_rms=pcm_rms,
                stt_elapsed_ms=stt_elapsed_ms,
                model_revision=getattr(stt_result, "model_revision", None) or "",
                audio_rms=getattr(getattr(stt_result, "audio_quality", None), "rms", pcm_rms),
            )
            await self.media.emit(
                RuntimeEvent(
                    self.call_id,
                    RuntimeEventType.STT_FINAL,
                    {"utterance_id": utterance_id, "text": text},
                )
            )
            await self._emit_stage(
                "stt.final", utterance_id=utterance_id, text_len=len(text)
            )
            if not raw_text:
                await self._emit_stage(
                    "stt.empty",
                    utterance_id=utterance_id,
                    duration_ms=duration_ms,
                    pcm_rms=pcm_rms,
                    model_revision=stt_result.model_revision or "",
                    empty_reason="gigaam_blank",
                )
            if not text or self._is_assistant_echo(text):
                if text:
                    await self._emit_stage(
                        "stt.echo_discarded",
                        utterance_id=utterance_id,
                        text_len=len(text),
                    )
                    await self._emit_forensic_turn(
                        utterance_id=utterance_id,
                        stt_text=text,
                        stt_rms=pcm_rms,
                        stt_duration_ms=duration_ms,
                        stt_latency_ms=stt_elapsed_ms,
                        dump_path=dump_path or "",
                        delivered_slot=self.session.state.pending_slot or "",
                        interpret_path="echo_discarded",
                        interpret_latency_ms=0,
                        stt_request_ts=stt_request_ts,
                        stt_result_ts=stt_result_ts,
                    )
                    self._reset_uplink_endpointing()
                self._resume_answer_wait_if_paused()
                self._turn_manager.on_turn_applied()
                await self._submit_utterance_outcome(
                    _UtteranceOutcome(
                        utterance_seq=utterance_seq,
                        utterance_id=utterance_id,
                        ok=False,
                    )
                )
                return

            await self._cancel_wait_timer()

            answer_slot = None
            if self.session.uses_dialogue_engine() and self.session._engine:
                answer_slot = self.session._engine.answer_context_slot()
            else:
                answer_slot = (
                    self.session.state.delivered_answer_slot
                    or self.session.state.pending_slot
                )

            rich_turn = None
            fast_confident = False
            contextual_confident = False
            rules_confident = False
            interpret_path = "unknown"
            force_rich = should_use_rich_turn(
                text, answer_slot, is_topic_slot_fn=is_topic_slot
            )
            if self.session.uses_dialogue_engine():
                ctx = InterpretContext.from_engine_state(
                    self.session._engine.state, turn_id=utterance_id
                )
                if not force_rich:
                    sem, contextual_confident = contextual_interpret(text, ctx)
                    fast_confident = contextual_confident
                    if contextual_confident:
                        interpret_path = "fast_contextual"
                    if not fast_confident:
                        sem, rules_confident = fast_interpret_semantic(
                            text, answer_slot=answer_slot
                        )
                        fast_confident = rules_confident
                        if rules_confident:
                            interpret_path = "fast_rules"
                    if fast_confident:
                        interp = semantic_to_interpretation(sem)
                        await self._emit_stage(
                            "interpret.fast_path",
                            utterance_id=utterance_id,
                            answer_slot=answer_slot or "",
                        )
                else:
                    interpret_path = "rich_required"
            llm_request_id = f"llm-{uuid.uuid4().hex[:8]}"
            self._active_llm_request_id = llm_request_id
            semantic_payload = None
            try:
                if not fast_confident:
                    ctx = build_turn_context(
                        self.session.state,
                        turn_id=turn_id,
                        utterance_id=utterance_id,
                        raw_text=text,
                        asr_quality=stt_result.asr_quality,
                        delivered_phrases=tuple(self._delivered_phrases[-6:]),
                    )
                    try:
                        semantic_payload = await self.llm.interpret_turn(
                            ctx,
                            deadline=budget.deadline,
                            request_id=llm_request_id,
                        )
                    except Exception as exc:
                        log.warning(
                            "LLM interpret failed call_id=%s utterance=%s: %s — rule fallback",
                            self.call_id,
                            utterance_id,
                            exc,
                        )
            finally:
                if self._active_llm_request_id == llm_request_id:
                    self._active_llm_request_id = None

            if self._stopped or self._transport_closed:
                self._inflight_utterances.discard(utterance_seq)
                return

            interpret_ready_ms = int((time.monotonic() - budget.started_mono) * 1000)
            await self._emit_stage(
                "interpret.ready",
                utterance_id=utterance_id,
                elapsed_ms=interpret_ready_ms,
            )
            await self.media.emit(
                RuntimeEvent(self.call_id, RuntimeEventType.INTERPRETATION_READY, {})
            )
            qkind = active_question_kind(self.session.state)
            if semantic_payload is not None:
                interpret_path = "llm"
                interp, _validated = adapt_semantic_turn(
                    text,
                    semantic_payload.payload,
                    state=self.session.state,
                    active_question_kind=qkind,
                    pending_slot=answer_slot,
                )
                if self.session.uses_dialogue_engine():
                    rich_turn = payload_to_rich_turn(
                        _validated.payload,
                        utterance_id=utterance_id,
                        raw_text=text,
                    )
            elif not fast_confident:
                interpret_path = "rules_fallback"
                from packages.dialogue.interpretation import interpret_user_turn

                interp = interpret_user_turn(self.session.state, text)
                if self.session.uses_dialogue_engine() and force_rich:
                    from packages.dialogue_engine.turn_understanding import (
                        build_rich_turn_from_text,
                    )

                    rich_turn = build_rich_turn_from_text(
                        text, utterance_id=utterance_id
                    )
            await self._emit_forensic_turn(
                utterance_id=utterance_id,
                stt_text=text,
                stt_rms=pcm_rms,
                stt_duration_ms=duration_ms,
                stt_latency_ms=stt_elapsed_ms,
                dump_path=dump_path or "",
                delivered_slot=answer_slot or self.session.state.pending_slot or "",
                interpret_path=interpret_path,
                interpret_latency_ms=interpret_ready_ms,
                stt_request_ts=stt_request_ts,
                stt_result_ts=stt_result_ts,
            )
            if stt_result.asr_quality in (AsrQuality.LOW, AsrQuality.UNUSABLE):
                await self._emit_stage(
                    "stt.low_quality",
                    utterance_id=utterance_id,
                    quality=str(stt_result.asr_quality),
                )
            legacy_contract: TurnInterpretation = to_turn_interpretation(
                self.session.state,
                turn_id,
                text,
                interp,
                state_version=self.session.state.state_version,
                asr_quality=stt_result.asr_quality,
            )
            await self._submit_utterance_outcome(
                _UtteranceOutcome(
                    utterance_seq=utterance_seq,
                    utterance_id=utterance_id,
                    ok=True,
                    text=text,
                    interp=interp,
                    legacy_contract=legacy_contract,
                    rich_turn=rich_turn,
                    asr_quality=stt_result.asr_quality,
                )
            )
        finally:
            self._utterance_budgets.pop(utterance_seq, None)
            if self._active_stage_budget == budget:
                self._active_stage_budget = None

    async def _speak_validated_proposal(
        self,
        result: SessionTurnResult,
        speech: str,
        render_generation: str,
    ) -> bool:
        proposal = TurnProposal(
            turn_id=result.proposal.turn_id,
            generation_id=result.proposal.generation_id,
            speech=speech,
            intent=result.proposal.intent,
            fsm_state=result.proposal.fsm_state,
            mandatory_remaining=result.proposal.mandatory_remaining,
        )
        validated = Validator.validate(proposal)
        if not validated.allowed or not validated.speech:
            return False
        if self._render_generation != render_generation:
            return False
        self._last_delivered_intent = result.proposal.intent
        if result.proposal.intent == "opening_wellness":
            # region agent log
            agent_debug_log(
                "B",
                "call_actor.py:_speak_validated_proposal",
                "opening_intent_set",
                {"call_id": self.call_id, "intent": result.proposal.intent},
            )
            # endregion
        marks_delivered = result.proposal.intent.startswith(
            ("check_", "clarify_", "repeat_")
        ) or result.proposal.intent == "opening_wellness"
        if result.from_engine and result.speak_effect is not None:
            self._pending_mark_spoken_id = result.speak_effect.generation_id
            self._pending_speak_effect_id = result.speak_effect.effect_id
            self._pending_mark_render_gen = render_generation
            if self.session._engine is not None:
                self.session._engine.outbox.mark_started(result.speak_effect.effect_id)
        elif marks_delivered:
            self._pending_mark_spoken_id = result.proposal.generation_id
            self._pending_mark_render_gen = render_generation
        mandatory_wait_intents = (
            "opening_wellness",
            "confirm_identity",
            "repeat_identity",
            "confirm_consent",
            "check_can_talk",
        )
        if not self.session.uses_dialogue_engine() and (
            result.proposal.intent.startswith(("check_", "clarify_", "repeat_"))
            or result.proposal.intent in mandatory_wait_intents
        ):
            # Arm before speak — cached opening drains + finalizes inside speak;
            # setting this afterward leaves Vera with no answer-wait (test + live).
            self._pending_answer_wait = (
                result.proposal.question_goal_id,
                result.proposal.generation_id,
            )
        cached = (
            load_opening(validated.speech)
            if result.proposal.intent == "opening_wellness"
            else None
        )
        if cached is not None:
            await self._speak_cached_pcm(
                validated.speech,
                cached.pcm_s16le,
                cached.sample_rate,
                render_generation,
            )
        else:
            await self._speak_phrase(validated.speech, render_generation)
        return True

    async def _deliver_followup_speaks(
        self,
        result: SessionTurnResult,
        render_generation: str,
    ) -> None:
        for fx in result.followup_speak_effects:
            if not isinstance(fx, SpeakEffect):
                continue
            if self.session.uses_dialogue_engine():
                valid = await asyncio.to_thread(self.session.is_engine_speak_valid, fx)
                if not valid:
                    await self._on_stale_speak_effect(
                        fx,
                        intent=fx.intent,
                        reason="followup",
                    )
                    continue
            sub = SessionTurnResult(
                user_text=result.user_text,
                interpretation=result.interpretation,
                turn_contract=result.turn_contract,
                proposal=result.proposal.model_copy(
                    update={
                        "generation_id": fx.generation_id,
                        "speech": fx.text,
                        "intent": fx.intent,
                    }
                ),
                validated=result.validated.model_copy(update={"speech": fx.text}),
                safety=result.safety,
                from_engine=True,
                speak_effect=fx,
            )
            await self._speak_validated_proposal(sub, fx.text, render_generation)

    async def _deliver_session_turn(self, result: SessionTurnResult) -> None:
        if result.proposal.intent == "wait_for_continuation":
            if self.session.uses_dialogue_engine() and result.timer_effect is not None:
                await self._schedule_engine_timer(result.timer_effect)
                return
            await self._handle_backchannel_continuation(result)
            return
        if self.session.uses_dialogue_engine():
            await self._cancel_engine_timer()
        await self._cancel_wait_timer()
        self._outbox_action_id = result.proposal.generation_id
        if result.proposal.intent == "pause_ack":
            if self._stopped or self._transport_closed or not result.validated.allowed:
                return
            await self._speak_validated_proposal(
                result, result.validated.speech, result.proposal.generation_id
            )
            self._start_pause_wait()
            return
        await self._cancel_wait_timer()
        if self._stopped or self._transport_closed or not result.validated.allowed:
            return
        planner_text = result.validated.speech
        if not planner_text:
            return

        render_generation = f"g-{uuid.uuid4().hex[:8]}"
        self._render_generation = render_generation
        self._playback_turn_generation = None
        render_deadline = time.monotonic() + self.config.llm_deadline_s

        if result.from_engine or result.proposal.intent in ENGINE_SPEAK_INTENTS:
            await self._speak_validated_proposal(result, planner_text, render_generation)
            await self._deliver_followup_speaks(result, render_generation)
            return

        facts = [
            {
                "field": k,
                "value": v.value,
                "quote": v.source_quote,
                "source_utterance_id": v.source_utterance_id,
            }
            for k, v in self.session.state.facts.items()
        ]
        action = {
            "intent": result.proposal.intent,
            "fsm_state": result.proposal.fsm_state.value,
            "planner_text": planner_text,
            "user_text": result.user_text,
            "pending_question": self.session.state.pending_question,
            "delivered_phrases": list(self._delivered_phrases[-6:]),
        }
        render_request_id = f"render-{uuid.uuid4().hex[:8]}"
        self._active_llm_request_id = render_request_id
        buffer = ""
        stream_spoken_parts: list[str] = []
        first_phrase_started = False
        self._hold_turn_finalize = True
        try:
            async for chunk in self.llm.render_stream(
                action,
                facts,
                render_deadline,
                request_id=render_request_id,
            ):
                if (
                    self._render_generation != render_generation
                    or self._stopped
                    or self._transport_closed
                ):
                    return
                if chunk.delta:
                    buffer += chunk.text
                    phrases, buffer = self._split_complete_phrases(buffer)
                    for phrase in phrases:
                        if await self._speak_validated_proposal(
                            result, phrase, render_generation
                        ):
                            stream_spoken_parts.append(phrase)
                            first_phrase_started = True
                            await self._emit_stage(
                                "render.first_phrase",
                                phrase_len=len(phrase),
                            )
                elif chunk.done:
                    done_text = (chunk.text or buffer).strip()
                    confirmed = " ".join(stream_spoken_parts).strip()
                    if not first_phrase_started and done_text:
                        await self._speak_validated_proposal(
                            result, done_text, render_generation
                        )
                    elif done_text and done_text != confirmed:
                        if confirmed and done_text.startswith(confirmed):
                            remainder = done_text[len(confirmed) :].strip().lstrip(".")
                            if remainder:
                                await self._speak_validated_proposal(
                                    result, remainder, render_generation
                                )
                        elif buffer.strip() and buffer.strip() not in stream_spoken_parts:
                            await self._speak_validated_proposal(
                                result, buffer.strip(), render_generation
                            )
                    await self._emit_stage("render.complete")
                    break
        except Exception:
            if not first_phrase_started:
                await self._speak_validated_proposal(
                    result, planner_text, render_generation
                )
        finally:
            self._hold_turn_finalize = False
            if self._active_llm_request_id == render_request_id:
                self._active_llm_request_id = None

        if self._render_generation != render_generation or self._stopped:
            return
        if buffer.strip() and not first_phrase_started:
            await self._speak_validated_proposal(
                result, buffer.strip(), render_generation
            )
        if self._playback and self._playback.playback_complete():
            await self._finalize_turn_playback()

    async def _interrupt_playback(self, *, flush: bool) -> None:
        if flush:
            self._bump_control_epoch()
            asyncio.create_task(self.media.flush())
        await self._cancel_active_llm()
        self._hold_turn_finalize = False
        self._render_generation = None
        self._playback_turn_generation = None
        sent_samples = 0
        interrupted_text = ""
        if self._playback and self._playback._ledger:
            sent_samples = self._playback._ledger.sent_samples
            interrupted_text = self._playback._ledger.canonical_text or ""
        if self._outbox_action_id:
            await self._finalize_outbox_action(
                sent_samples=sent_samples,
                outcome="cancelled",
            )
        if not self._playback or not self._active_generation:
            return
        gen = self._active_generation
        # Remember partial speech so post-interrupt STT echo is discarded.
        if sent_samples > 0 and interrupted_text:
            self._remember_assistant_phrase(interrupted_text)
        self._playback.cancel_generation(gen)
        asyncio.create_task(self.tts.cancel(gen))
        if self._tts_task and not self._tts_task.done():
            self._tts_task.cancel()
        await self.media.emit(
            RuntimeEvent(
                self.call_id,
                RuntimeEventType.PLAYBACK_INTERRUPTED,
                {"generation_id": gen},
            )
        )
        self._active_generation = None
        self._force_listen_enabled()
        self._playback_uplink_buf.clear()
        self._tts_resamplers = {
            k: v for k, v in self._tts_resamplers.items() if not k.startswith(gen)
        }

    async def _speak_cached_pcm(
        self,
        text: str,
        pcm: bytes,
        sample_rate: int,
        render_generation: str,
    ) -> None:
        """Play pre-rendered opening — no TTS HTTP wait on warm calls."""
        if (
            not pcm
            or not self._playback
            or self._stopped
            or self._transport_closed
            or self._render_generation != render_generation
        ):
            return
        generation_id = render_generation
        phrase_id = f"p-cache-{uuid.uuid4().hex[:8]}"
        new_turn = self._playback_turn_generation != render_generation
        self._active_generation = generation_id
        self._on_bot_playback_started()
        self._playback.begin_phrase(
            generation_id, phrase_id, text, new_turn=new_turn
        )
        self._playback_turn_generation = render_generation
        await self._emit_stage(
            "tts.start",
            phrase_id=phrase_id,
            text_len=len(text),
            cached=True,
        )
        seq = 0
        frame_samples = max(1, self._output_sample_rate * self.config.frame_ms // 1000)
        frame_bytes = frame_samples * 2
        offset = 0
        first_logged = False
        while offset < len(pcm):
            if (
                generation_id != self._active_generation
                or self._render_generation != render_generation
                or self._stopped
            ):
                break
            chunk_pcm = pcm[offset : offset + frame_bytes * 4]
            offset += len(chunk_pcm)
            out_pcm = self._resample_tts_chunk(
                generation_id, chunk_pcm, sample_rate
            )
            if not first_logged and out_pcm:
                first_logged = True
                await self._emit_stage(
                    "tts.first_pcm",
                    generation_id=generation_id,
                    samples=len(out_pcm) // 2,
                    cached=True,
                )
            if out_pcm and self._effective_echo_ref_gate():
                self._push_echo_downlink(out_pcm, self._output_sample_rate)
            env = AudioEnvelope(
                call_id=self.call_id,
                generation_id=generation_id,
                phrase_id=phrase_id,
                sequence=seq,
                sample_rate=self._output_sample_rate,
                pcm_s16le=out_pcm,
            )
            seq += 1
            if self._playback:
                await self._playback.enqueue_wait(env)
        if self._playback and generation_id == self._active_generation:
            self._playback.mark_generation_done("success")
        await self._wait_phrase_playback_drained()

    def _clear_pending_delivery(self, render_generation: str) -> None:
        if self._pending_mark_render_gen == render_generation:
            self._pending_mark_spoken_id = None
            self._pending_mark_render_gen = None
        if self._outbox_action_id and self._pending_answer_wait is not None:
            self._pending_answer_wait = None

    async def _abort_undelivered_phrase(self, render_generation: str) -> None:
        """Release ledger reservation when TTS/playback never sent audio."""
        self._clear_pending_delivery(render_generation)
        sent_samples = 0
        if self._playback and self._playback._ledger:
            sent_samples = self._playback._ledger.sent_samples
        if sent_samples > 0:
            return
        if self._outbox_action_id:
            await self._finalize_outbox_action(
                sent_samples=0,
                outcome="cancelled",
            )
            return
        action_id = self._pending_mark_spoken_id or render_generation
        if self.session.uses_dialogue_engine():
            await asyncio.to_thread(
                self.session.cancel_playout_action, action_id
            )
            return
        await asyncio.to_thread(
            Planner.release_question_attempt,
            self.session.state,
            action_id,
        )

    async def _wait_phrase_playback_drained(self) -> None:
        if not self._playback:
            return
        render_generation = self._render_generation
        deadline = time.monotonic() + self.config.tts_deadline_s + 10.0
        while time.monotonic() < deadline:
            if self._stopped or self._transport_closed:
                return
            ledger = self._playback._ledger
            if ledger and ledger.generation_done and ledger.generation_outcome not in (
                None,
                "success",
            ):
                if ledger.generation_outcome == "failed":
                    await self._fail_pending_speak_playout("playout_failed")
                if render_generation:
                    await self._abort_undelivered_phrase(render_generation)
                if not self._hold_turn_finalize:
                    self._active_generation = None
                return
            if self._playback.playback_complete():
                await self._on_playback_drained()
                return
            await asyncio.sleep(0.01)
        log.warning(
            "phrase playback drain timeout call_id=%s generation=%s",
            self.call_id,
            self._active_generation,
        )

    async def _speak_phrase(self, text: str, render_generation: str) -> None:
        if (
            not text
            or not self._playback
            or self._stopped
            or self._transport_closed
            or self._render_generation != render_generation
        ):
            return
        generation_id = render_generation
        phrase_id = f"p-{uuid.uuid4().hex[:8]}"
        new_turn = self._playback_turn_generation != render_generation
        self._active_generation = generation_id
        self._on_bot_playback_started()
        self._playback.begin_phrase(
            generation_id, phrase_id, text, new_turn=new_turn
        )
        self._playback_turn_generation = render_generation
        deadline = time.monotonic() + self.config.tts_deadline_s
        seq = 0

        async def _run_tts() -> None:
            nonlocal seq
            outcome = "success"
            try:
                async for chunk in self.tts.synthesize(
                    text,
                    call_id=self.call_id,
                    generation_id=generation_id,
                    phrase_id=phrase_id,
                    deadline=deadline,
                ):
                    if (
                        generation_id != self._active_generation
                        or self._render_generation != render_generation
                        or self._stopped
                    ):
                        outcome = "cancelled"
                        break
                    out_pcm = self._resample_tts_chunk(
                        generation_id, chunk.pcm_s16le, chunk.sample_rate
                    )
                    env = AudioEnvelope(
                        call_id=self.call_id,
                        generation_id=generation_id,
                        phrase_id=phrase_id,
                        sequence=seq,
                        sample_rate=self._output_sample_rate,
                        pcm_s16le=out_pcm,
                    )
                    seq += 1
                    if self._playback:
                        enqueued = await self._playback.enqueue_wait(env)
                        if not enqueued:
                            outcome = "cancelled" if outcome == "success" else outcome
                            break
            except asyncio.CancelledError:
                outcome = "cancelled"
                raise
            except Exception as exc:
                outcome = "failed"
                log.error(
                    "TTS failed call_id=%s generation_id=%s phrase_id=%s: %s",
                    self.call_id,
                    generation_id,
                    phrase_id,
                    exc,
                )
                if self._pending_speak_effect_id and self.session.uses_dialogue_engine():
                    await asyncio.to_thread(
                        self.session.handle_effect_failed,
                        self._pending_speak_effect_id,
                        stage="TTS",
                        error=str(exc)[:200],
                    )
                await self._emit_stage(
                    "tts.failed",
                    generation_id=generation_id,
                    phrase_id=phrase_id,
                    error=str(exc)[:200],
                )
            finally:
                if self._playback and generation_id == self._active_generation:
                    for key, resampler in list(self._tts_resamplers.items()):
                        if not key.startswith(f"{generation_id}:"):
                            continue
                        tail_pcm = resampler.flush()
                        if tail_pcm:
                            tail_env = AudioEnvelope(
                                call_id=self.call_id,
                                generation_id=generation_id,
                                phrase_id=phrase_id,
                                sequence=seq,
                                sample_rate=self._output_sample_rate,
                                pcm_s16le=tail_pcm,
                            )
                            seq += 1
                            if not await self._playback.enqueue_wait(tail_env):
                                outcome = "cancelled"
                    flush_env = AudioEnvelope(
                        call_id=self.call_id,
                        generation_id=generation_id,
                        phrase_id=phrase_id,
                        sequence=seq,
                        sample_rate=self._output_sample_rate,
                        pcm_s16le=b"",
                    )
                    if not await self._playback.flush_carried_frames(flush_env):
                        outcome = "cancelled"
                    self._playback.mark_generation_done(outcome)

        self._tts_task = asyncio.create_task(_run_tts())
        if self._tts_slow_watch and not self._tts_slow_watch.done():
            self._tts_slow_watch.cancel()
        self._tts_slow_watch = asyncio.create_task(
            self._watch_tts_slow_start(generation_id, phrase_id)
        )
        await self._emit_stage("tts.start", phrase_id=phrase_id, text_len=len(text))
        await self.media.emit(
            RuntimeEvent(
                self.call_id,
                RuntimeEventType.RENDERER_PHRASE_READY,
                {"phrase_id": phrase_id, "text": text, "generation_id": generation_id},
            )
        )
        try:
            await self._tts_task
        except asyncio.CancelledError:
            return
        await self._wait_phrase_playback_drained()

    async def _watch_tts_slow_start(self, generation_id: str, phrase_id: str) -> None:
        try:
            await asyncio.sleep(5.0)
        except asyncio.CancelledError:
            return
        if generation_id in self._tts_first_pcm_gens:
            return
        if self._active_generation != generation_id:
            return
        log.error(
            "TTS slow start call_id=%s generation_id=%s phrase_id=%s — no first_pcm in 5s",
            self.call_id,
            generation_id,
            phrase_id,
        )
        await self._emit_stage(
            "tts.slow_start",
            generation_id=generation_id,
            phrase_id=phrase_id,
            waited_ms=5000,
        )

    async def _playback_pump(self) -> None:
        assert self._playback
        while not self._stopped:
            chunk = self._playback.pop_nowait()
            if chunk is None:
                if self._playback.playback_complete():
                    await self._on_playback_drained()
                await asyncio.sleep(0.01)
                continue
            try:
                await self.media.send_pcm(chunk.pcm_s16le)
            except Exception as exc:
                if self._playback._ledger:
                    self._playback._ledger.generation_outcome = "failed"
                    self._playback.mark_generation_done("failed")
                await self._fail_pending_speak_playout(str(exc))
                await self._emit_stage(
                    "playout.failed",
                    generation_id=chunk.generation_id,
                    error=str(exc)[:200],
                )
                continue
            if self._effective_echo_ref_gate():
                self._push_echo_downlink(chunk.pcm_s16le, chunk.sample_rate)
            if chunk.sequence == 0:
                self._tts_first_pcm_gens.add(chunk.generation_id)
                if self._tts_slow_watch and not self._tts_slow_watch.done():
                    self._tts_slow_watch.cancel()
                await self._emit_stage(
                    "tts.first_pcm",
                    generation_id=chunk.generation_id,
                    samples=len(chunk.pcm_s16le) // 2,
                )
            if not self.config.telephony_stream:
                duration = (len(chunk.pcm_s16le) // 2) / chunk.sample_rate
                await asyncio.sleep(duration)

    async def _on_playback_drained(self) -> None:
        assert self._playback
        gen = self._active_generation
        if not gen or not self._playback.playback_complete():
            return
        ledger = self._playback._ledger
        if not ledger:
            return
        if ledger.sent_samples <= 0 or ledger.generation_outcome != "success":
            if ledger.generation_outcome == "failed":
                await self._fail_pending_speak_playout("playout_drain_failed")
            if not self._hold_turn_finalize:
                self._active_generation = None
                self._force_listen_enabled()
            return
        spoken = ledger.canonical_text
        self._remember_assistant_phrase(spoken or "")
        if self._hold_turn_finalize:
            return
        await self._finalize_turn_playback()

    async def _finalize_turn_playback(self) -> None:
        assert self._playback
        pending_wait: tuple[str | None, str | None] | None = None
        playout_followup: SessionTurnResult | None = None
        async with self._finalize_lock:
            gen = self._active_generation
            if not gen or not self._playback.playback_complete():
                return
            if gen in self._finalized_playback_gens:
                # Already finalized — never leave mute stuck on a replay.
                if self._active_generation == gen:
                    self._active_generation = None
                self._force_listen_enabled()
                return
            ledger = self._playback._ledger
            if not ledger:
                self._active_generation = None
                self._force_listen_enabled()
                return
            if ledger.sent_samples <= 0 or ledger.generation_outcome != "success":
                if ledger.generation_outcome == "failed":
                    await self._fail_pending_speak_playout("playout_finalize_failed")
                self._active_generation = None
                self._force_listen_enabled()
                return
            self._playback.mark_completed()
            intent = self._last_delivered_intent or ""
            marks_question = intent in _QUESTION_DELIVERY_INTENTS or intent.startswith(
                ("check_", "clarify_", "repeat_")
            )
            if marks_question:
                self.session.state.pending_question_delivered = True
            if (
                self._pending_mark_render_gen == gen
                and self._pending_mark_spoken_id
                and ledger.sent_samples > 0
            ):
                await asyncio.to_thread(
                    self.session.mark_spoken_action, self._pending_mark_spoken_id
                )
                playout_followup = await asyncio.to_thread(
                    self.session.pop_engine_playout_followup
                )
                self._pending_mark_spoken_id = None
                self._pending_mark_render_gen = None
            finish = self.media.finish or self.media.flush
            await finish()
            sent = ledger.sent_samples
            await self._finalize_outbox_action(
                sent_samples=sent, outcome=ledger.generation_outcome
            )
            await self.media.emit(
                RuntimeEvent(
                    self.call_id,
                    RuntimeEventType.PLAYBACK_COMPLETED,
                    {
                        "generation_id": gen,
                        "sent_samples": ledger.sent_samples,
                        "queued_samples": ledger.queued_samples,
                        "generated_samples": ledger.generated_samples,
                    },
                )
            )
            self._forensic_bot_playout_end_ts = utc_now_iso()
            self._finalized_playback_gens.add(gen)
            # Drop generation mute BEFORE pause await so a cancelled pause
            # cannot leave Vera permanently deaf (sip-97e9d693a5).
            self._arm_post_speech_pause()
            self._active_generation = None
            self._tts_resamplers = {
                k: v
                for k, v in self._tts_resamplers.items()
                if not k.startswith(gen)
            }
            pending_wait = self._pending_answer_wait
            self._pending_answer_wait = None

        await self._enable_listen_after_playback()
        if pending_wait is not None and not self.session.uses_dialogue_engine():
            self._start_answer_wait(
                goal_id=pending_wait[0],
                question_id=pending_wait[1],
            )
        if playout_followup is not None:
            await self._post_apply_turn(playout_followup)
        await self._flush_deferred_engine_turn()
        await self._flush_pending_end_call_effect()

    async def _fail_pending_speak_playout(self, error: str) -> None:
        effect_id = self._pending_speak_effect_id
        if not effect_id or not self.session.uses_dialogue_engine():
            return
        await asyncio.to_thread(
            self.session.handle_effect_failed,
            effect_id,
            stage="PLAYOUT",
            error=error[:200],
        )
        self._pending_speak_effect_id = None

    async def _schedule_end_call_effect(self, effect: EndCallEffect) -> None:
        if await self._execute_end_call_effect(effect):
            return
        self._pending_end_call_effect = effect
        await self._emit_stage(
            "end_call.deferred",
            effect_id=effect.effect_id,
            reason=effect.reason,
        )

    async def _flush_pending_end_call_effect(self) -> None:
        effect = self._pending_end_call_effect
        if effect is None:
            return
        if await self._execute_end_call_effect(effect):
            self._pending_end_call_effect = None

    async def _execute_end_call_effect(self, effect: EndCallEffect) -> bool:
        if self._stopped or self._transport_closed:
            return False
        if self._active_generation or (self._playback and self._playback.pending_frames):
            return False
        if self._inflight_utterances:
            return False
        if self._tts_task and not self._tts_task.done():
            return False
        engine = self.session._engine
        if engine is not None:
            engine.outbox.mark_started(effect.effect_id)
        await self._emit_stage(
            "end_call.started",
            effect_id=effect.effect_id,
            reason=effect.reason,
        )
        await self._cancel_engine_timer()
        await self._cancel_wait_timer()
        self._transport_closed = True
        self._stopped = True
        await self.media.hangup()
        if engine is not None:
            engine.outbox.mark_completed(effect.effect_id)
        await self._emit_stage(
            "end_call.completed",
            effect_id=effect.effect_id,
            reason=effect.reason,
        )
        await self._verify_call_cleanup()
        return True

    async def _verify_call_cleanup(self) -> None:
        engine = self.session._engine
        if engine is None:
            return
        snap = engine.outbox.cleanup_snapshot()
        active_timers = (
            1 if self._engine_timer_task and not self._engine_timer_task.done() else 0
        )
        playout_active = 1 if self._active_generation else 0
        tts_active = 1 if self._tts_task and not self._tts_task.done() else 0
        issues = {
            k: v
            for k, v in {
                **snap,
                "active_timers": active_timers,
                "playout_active": playout_active,
                "tts_active": tts_active,
            }.items()
            if v
        }
        if issues:
            await self._emit_stage("CALL_CLEANUP_FAILURE", **issues)
        else:
            await self._emit_stage("call.cleanup_ok", **snap)


def build_call_actor(
    call_id: str,
    family_id: str,
    elder_name: str,
    stt_url: str,
    tts_url: str,
    llm_url: str,
    media: MediaCallbacks,
    *,
    store: object | None = None,
) -> CallActor:
    session = CallSession(
        call_id=call_id,
        family_id=family_id,
        elder_display_name=elder_name,
        store=store,
    )
    profile_audio = audio_settings()
    profile_limits = {}
    try:
        from packages.voice_runtime.profile import load_profile

        profile_limits = load_profile().get("limits") or {}
    except OSError:
        pass
    playback_buffer_ms = int(
        os.environ.get(
            "IMVERA_PLAYBACK_BUFFER_MS",
            str(profile_limits.get("playback_buffer_ms", 60)),
        )
    )
    shared = get_shared_async_client()
    return CallActor(
        call_id=call_id,
        family_id=family_id,
        session=session,
        stt=HttpSTTProvider(stt_url, client=shared),
        tts=HttpTTSProvider(tts_url, client=shared),
        llm=HttpLLMProvider(llm_url, client=shared),
        media=media,
        config=CallActorConfig(
            target_sample_rate=profile_audio["internal_sample_rate"],
            frame_ms=profile_audio["frame_ms"],
            playback_buffer_ms=playback_buffer_ms,
            telephony_stream=os.environ.get("IMVERA_TELEPHONY_STREAM", "1") == "1",
            lab_half_duplex=lab_half_duplex_enabled(),
            post_speech_pause_ms=post_speech_pause_ms(),
            uplink_preroll_ms=uplink_preroll_ms(),
            echo_ref_gate=echo_ref_gate_enabled(),
            lab_barge_in=lab_barge_in_enabled(),
        ),
    )
