"""Per-call voice actor — media-ready greeting, render path, barge-in, lifecycle."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from packages.contracts.core import TerminationReason
from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.outbox import ActionOutboxStatus
from packages.contracts.providers import TTSProvider
from packages.contracts.runtime import RuntimeEvent, RuntimeEventType
from packages.contracts.turn import TurnProposal
from packages.dialogue.context_builder import active_question_kind, build_turn_context
from packages.dialogue.semantic_adapter import adapt_semantic_turn
from packages.dialogue.interpretation import to_turn_interpretation, interpret_user_turn
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue.validator import Validator
from packages.voice_runtime.audio import AudioEnvelope, StatefulResampler
from packages.voice_runtime.endpointing import SpeechSegmentCollector
from packages.voice_runtime.opening_cache import load_opening
from packages.voice_runtime.playback import PlaybackQueue
from packages.voice_runtime.profile import audio_settings, dialogue_timing_settings
from packages.voice_runtime.silero_vad import create_vad
from packages.voice_runtime.wait_state import DialogueTimingProfile, WaitState
from services.llm.http_provider import HttpLLMProvider
from services.providers.http_clients import get_shared_async_client
from services.stt.http_provider import HttpSTTProvider
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
    }
)
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
    _collector: SpeechSegmentCollector | None = None
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
    _hangup_after_playback: bool = False
    _transport_closed: bool = False
    _capture_lost: bool = False
    _active_llm_request_id: str | None = None
    _wait_task: asyncio.Task | None = None
    _wait_state: WaitState | None = None
    _control_epoch: int = 0
    _timing_profile: DialogueTimingProfile = field(
        default_factory=lambda: DialogueTimingProfile(**dialogue_timing_settings())
    )
    _monotonic: Callable[[], float] = field(default=time.monotonic, repr=False)
    _outbox_action_id: str | None = None
    _pending_answer_wait: tuple[str | None, str | None] | None = None
    _pending_mark_spoken_id: str | None = None
    _pending_mark_render_gen: str | None = None
    _last_delivered_intent: str | None = None
    _playback_uplink_buf: bytearray = field(default_factory=bytearray)
    _tts_first_pcm_gens: set[str] = field(default_factory=set)
    _tts_slow_watch: asyncio.Task | None = None

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
        self._collector = SpeechSegmentCollector(self.config.target_sample_rate)

    def _flush_pcm_queue(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _reset_uplink_endpointing(self) -> None:
        """Clear VAD/collector after assistant playback — fresh listen window."""
        if self._input_resampler is None:
            return
        self._vad = create_vad(self.config.target_sample_rate)
        self._collector = SpeechSegmentCollector(self.config.target_sample_rate)

    @staticmethod
    def _normalize_speech_text(text: str) -> str:
        cleaned = re.sub(r"[^\w\s]", " ", text.lower())
        return " ".join(cleaned.split())

    def _is_assistant_echo(self, text: str) -> bool:
        normalized = self._normalize_speech_text(text)
        if not normalized:
            return True
        for phrase in self._delivered_phrases:
            spoken = self._normalize_speech_text(phrase)
            if not spoken:
                continue
            if normalized == spoken or spoken in normalized or normalized in spoken:
                return True
        pending = self.session.state.pending_question
        if pending:
            question = self._normalize_speech_text(pending)
            if question and (normalized == question or question in normalized):
                return True
        return False

    async def _feed_uplink_pcm(self, pcm: bytes) -> None:
        assert self._vad and self._collector
        started, ended = self._vad.feed(pcm)
        if started:
            if self._active_generation:
                await self._interrupt_playback(flush=True)
            self._pause_answer_wait()
            await self.media.emit(
                RuntimeEvent(self.call_id, RuntimeEventType.SPEECH_STARTED, {})
            )
        segment = self._collector.on_frame(pcm, started, ended)
        if segment:
            await self.media.emit(
                RuntimeEvent(self.call_id, RuntimeEventType.SPEECH_ENDED, {})
            )
            async with self._policy_lock:
                utterance_seq = self._utterance_seq + 1
                self._utterance_seq = utterance_seq
            self._inflight_utterances.add(utterance_seq)
            asyncio.create_task(self._handle_utterance(segment, utterance_seq))

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
        await self._feed_uplink_pcm(pcm)

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
                )
                deliver_results.append(result)
        for event in failed_events:
            await self.media.emit(event)
        for result in deliver_results:
            await self._post_apply_turn(result)

    def _bump_control_epoch(self) -> int:
        self._control_epoch += 1
        return self._control_epoch

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
        if (
            result.proposal.intent.endswith("_final")
            or result.proposal.intent == "partial_unresolved_close"
            or self.session.state.final_action_done
        ):
            self._hangup_after_playback = True
        if self._inflight_utterances:
            return
        await self._deliver_session_turn(result)

    async def _handle_utterance(self, pcm: bytes, utterance_seq: int) -> None:
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
        await self._emit_stage("utterance.start", utterance_id=utterance_id, turn_id=turn_id)
        try:
            try:
                stt_result = await self.stt.transcribe_final(
                    pcm,
                    self.config.target_sample_rate,
                    call_id=self.call_id,
                    turn_id=turn_id,
                    deadline=budget.deadline,
                )
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

            text = (stt_result.text or "").strip()
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
            if not text or self._is_assistant_echo(text):
                if text:
                    await self._emit_stage(
                        "stt.echo_discarded",
                        utterance_id=utterance_id,
                        text_len=len(text),
                    )
                self._resume_answer_wait_if_paused()
                await self._submit_utterance_outcome(
                    _UtteranceOutcome(
                        utterance_seq=utterance_seq,
                        utterance_id=utterance_id,
                        ok=False,
                    )
                )
                return

            await self._cancel_wait_timer()

            llm_request_id = f"llm-{uuid.uuid4().hex[:8]}"
            self._active_llm_request_id = llm_request_id
            ctx = build_turn_context(
                self.session.state,
                turn_id=turn_id,
                utterance_id=utterance_id,
                raw_text=text,
                asr_quality=stt_result.asr_quality,
                delivered_phrases=tuple(self._delivered_phrases[-6:]),
            )
            semantic = None
            try:
                semantic = await self.llm.interpret_turn(
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

            await self._emit_stage("interpret.ready", utterance_id=utterance_id)
            await self.media.emit(
                RuntimeEvent(self.call_id, RuntimeEventType.INTERPRETATION_READY, {})
            )
            qkind = active_question_kind(self.session.state)
            if semantic is not None:
                interp, _validated = adapt_semantic_turn(
                    text,
                    semantic.payload,
                    state=self.session.state,
                    active_question_kind=qkind,
                    pending_slot=self.session.state.pending_slot,
                )
            else:
                interp = interpret_user_turn(self.session.state, text)
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
        marks_delivered = result.proposal.intent.startswith(
            ("check_", "clarify_", "repeat_")
        ) or result.proposal.intent == "opening_wellness"
        if marks_delivered:
            self._pending_mark_spoken_id = result.proposal.generation_id
            self._pending_mark_render_gen = render_generation
        mandatory_wait_intents = (
            "confirm_identity",
            "repeat_identity",
            "confirm_consent",
            "check_can_talk",
        )
        if (
            result.proposal.intent.startswith(("check_", "clarify_", "repeat_"))
            or result.proposal.intent in mandatory_wait_intents
        ):
            self._pending_answer_wait = (
                result.proposal.question_goal_id,
                result.proposal.generation_id,
            )
        return True

    async def _deliver_session_turn(self, result: SessionTurnResult) -> None:
        if result.proposal.intent == "wait_for_continuation":
            await self._handle_backchannel_continuation(result)
            return
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
            if self._hangup_after_playback and not result.validated.speech:
                await self._maybe_hangup_when_idle()
            return
        planner_text = result.validated.speech
        if not planner_text:
            if self._hangup_after_playback:
                await self._maybe_hangup_when_idle()
            return

        render_generation = f"g-{uuid.uuid4().hex[:8]}"
        self._render_generation = render_generation
        self._playback_turn_generation = None
        render_deadline = time.monotonic() + self.config.llm_deadline_s

        if result.proposal.intent in _SKIP_RENDER_INTENTS:
            await self._speak_validated_proposal(result, planner_text, render_generation)
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
                    return
        except Exception:
            if not first_phrase_started:
                await self._speak_validated_proposal(
                    result, planner_text, render_generation
                )
        finally:
            if self._active_llm_request_id == render_request_id:
                self._active_llm_request_id = None

        if self._render_generation != render_generation or self._stopped:
            return
        if buffer.strip() and not first_phrase_started:
            await self._speak_validated_proposal(
                result, buffer.strip(), render_generation
            )

    async def _interrupt_playback(self, *, flush: bool) -> None:
        if flush:
            self._bump_control_epoch()
            asyncio.create_task(self.media.flush())
        await self._cancel_active_llm()
        self._render_generation = None
        self._playback_turn_generation = None
        sent_samples = 0
        if self._playback and self._playback._ledger:
            sent_samples = self._playback._ledger.sent_samples
        if self._outbox_action_id:
            await self._finalize_outbox_action(
                sent_samples=sent_samples,
                outcome="cancelled",
            )
        if not self._playback or not self._active_generation:
            return
        gen = self._active_generation
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
            self._playback.mark_generation_done(generation_id, outcome="success")

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
            await self.media.send_pcm(chunk.pcm_s16le)
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
            self._active_generation = None
            return
        self._playback.mark_completed()
        spoken = ledger.canonical_text
        if spoken and (not self._delivered_phrases or self._delivered_phrases[-1] != spoken):
            self._delivered_phrases.append(spoken)
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
            self._pending_mark_spoken_id = None
            self._pending_mark_render_gen = None
        finish = self.media.finish or self.media.flush
        await finish()
        sent = ledger.sent_samples
        await self._finalize_outbox_action(sent_samples=sent, outcome=ledger.generation_outcome)
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
        self._active_generation = None
        self._tts_resamplers = {
            k: v for k, v in self._tts_resamplers.items() if not k.startswith(gen)
        }
        self._flush_pcm_queue()
        self._playback_uplink_buf.clear()
        self._reset_uplink_endpointing()
        pending_wait = self._pending_answer_wait
        if pending_wait is not None:
            self._pending_answer_wait = None
            self._start_answer_wait(
                goal_id=pending_wait[0],
                question_id=pending_wait[1],
            )
        if self._hangup_after_playback:
            await self._maybe_hangup_when_idle()

    async def _maybe_hangup_when_idle(self) -> None:
        if self._stopped or self._transport_closed:
            return
        if self._active_generation or (self._playback and self._playback.pending_frames):
            return
        if self._inflight_utterances:
            return
        if self._tts_task and not self._tts_task.done():
            return
        self._transport_closed = True
        await self.media.hangup()


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
        ),
    )
