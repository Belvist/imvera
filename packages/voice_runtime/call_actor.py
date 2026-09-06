"""Per-call voice actor — media-ready greeting, render path, barge-in, lifecycle."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from packages.contracts.core import TerminationReason
from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.providers import TTSProvider
from packages.contracts.runtime import RuntimeEvent, RuntimeEventType
from packages.contracts.turn import TurnProposal
from packages.dialogue.context_builder import active_question_kind, build_turn_context
from packages.dialogue.interpretation import to_turn_interpretation
from packages.dialogue.semantic_bridge import semantic_to_user_interpretation
from packages.dialogue.session import CallSession, SessionTurnResult
from packages.dialogue.validator import Validator
from packages.voice_runtime.audio import AudioEnvelope, StatefulResampler
from packages.voice_runtime.endpointing import SpeechSegmentCollector
from packages.voice_runtime.playback import PlaybackQueue
from packages.voice_runtime.profile import audio_settings
from packages.voice_runtime.silero_vad import create_vad
from services.llm.http_provider import HttpLLMProvider
from services.stt.http_provider import HttpSTTProvider
from services.tts.http_provider import HttpTTSProvider

log = logging.getLogger("call_actor")

_SKIP_RENDER_INTENTS = frozenset(
    {"greeting", "confirm_identity", "confirm_consent", "check_can_talk"}
)

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
    _hangup_after_playback: bool = False
    _transport_closed: bool = False
    _capture_lost: bool = False

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
        await self._ensure_output_chain(output_sample_rate, output_frame_size)
        if input_sample_rate is not None:
            await self._ensure_input_chain(input_sample_rate)
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
        if self._active_generation:
            return
        started, ended = self._vad.feed(pcm)
        if started:
            await self._interrupt_playback(flush=True)
            await self.media.emit(
                RuntimeEvent(self.call_id, RuntimeEventType.SPEECH_STARTED, {})
            )
        segment = self._collector.on_frame(pcm, started, ended)
        if segment:
            await self.media.emit(
                RuntimeEvent(self.call_id, RuntimeEventType.SPEECH_ENDED, {})
            )
            seq = self._utterance_seq + 1
            self._inflight_utterances.add(seq)
            asyncio.create_task(self._handle_utterance(segment, seq))

    async def _handle_utterance(self, pcm: bytes, utterance_seq: int) -> None:
        if self._stopped or self._transport_closed:
            self._inflight_utterances.discard(utterance_seq)
            return
        self._utterance_seq = utterance_seq
        utterance_id = f"u-{utterance_seq}"
        turn_id = self.session.turn_id + 1
        deadline = time.monotonic() + self.config.stt_deadline_s
        try:
            stt_result = await self.stt.transcribe_final(
                pcm,
                self.config.target_sample_rate,
                call_id=self.call_id,
                turn_id=turn_id,
                deadline=deadline,
            )
        except Exception as exc:
            self._inflight_utterances.discard(utterance_seq)
            if not self._stopped:
                await self.media.emit(
                    RuntimeEvent(
                        self.call_id,
                        RuntimeEventType.INTERPRETATION_FAILED,
                        {"error": str(exc), "stage": "stt"},
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
        if not text:
            self._inflight_utterances.discard(utterance_seq)
            return

        llm_deadline = time.monotonic() + self.config.llm_deadline_s
        ctx = build_turn_context(
            self.session.state,
            turn_id=turn_id,
            utterance_id=utterance_id,
            raw_text=text,
            asr_quality=stt_result.asr_quality,
            delivered_phrases=tuple(self._delivered_phrases[-6:]),
        )
        try:
            semantic = await self.llm.interpret_turn(ctx, deadline=llm_deadline)
        except Exception as exc:
            self._inflight_utterances.discard(utterance_seq)
            if not self._stopped:
                await self.media.emit(
                    RuntimeEvent(
                        self.call_id,
                        RuntimeEventType.INTERPRETATION_FAILED,
                        {"error": str(exc), "stage": "llm"},
                    )
                )
            return
        if self._stopped or self._transport_closed:
            self._inflight_utterances.discard(utterance_seq)
            return

        await self.media.emit(
            RuntimeEvent(self.call_id, RuntimeEventType.INTERPRETATION_READY, {})
        )
        qkind = active_question_kind(self.session.state)
        interp = semantic_to_user_interpretation(
            text,
            semantic.payload,
            active_question_kind=qkind,
            pending_slot=self.session.state.pending_slot,
        )
        legacy_contract: TurnInterpretation = to_turn_interpretation(
            self.session.state,
            turn_id,
            text,
            interp,
            state_version=self.session.state.state_version,
            asr_quality=stt_result.asr_quality,
        )

        async with self._policy_lock:
            while self._last_applied_utterance_seq + 1 < utterance_seq:
                await asyncio.sleep(0)
            if self._stopped or self._transport_closed:
                self._inflight_utterances.discard(utterance_seq)
                return
            result = await asyncio.to_thread(
                self.session.handle_user_text,
                text,
                interp=interp,
                contract=legacy_contract,
                utterance_id=utterance_id,
            )
            self._last_applied_utterance_seq = utterance_seq

        self._inflight_utterances.discard(utterance_seq)
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
        if result.proposal.intent.endswith("_final") or self.session.state.final_action_done:
            self._hangup_after_playback = True
        if self._inflight_utterances:
            return
        await self._deliver_session_turn(result)

    async def _deliver_session_turn(self, result: SessionTurnResult) -> None:
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

        rendered = planner_text
        try:
            if result.proposal.intent not in _SKIP_RENDER_INTENTS:
                facts = [
                    {
                        "field": k,
                        "value": v.value,
                        "quote": v.source_quote,
                        "source_utterance_id": v.source_utterance_id,
                    }
                    for k, v in self.session.state.facts.items()
                ]
                rendered_llm = await self.llm.render_text(
                    {
                        "intent": result.proposal.intent,
                        "fsm_state": result.proposal.fsm_state.value,
                        "planner_text": planner_text,
                        "user_text": result.user_text,
                        "pending_question": self.session.state.pending_question,
                        "delivered_phrases": list(self._delivered_phrases[-6:]),
                    },
                    facts,
                    time.monotonic() + self.config.llm_deadline_s,
                )
                if rendered_llm:
                    rendered = rendered_llm
        except Exception:
            rendered = planner_text

        if self._render_generation != render_generation or self._stopped or self._transport_closed:
            return

        proposal = TurnProposal(
            turn_id=result.proposal.turn_id,
            generation_id=result.proposal.generation_id,
            speech=rendered,
            intent=result.proposal.intent,
            fsm_state=result.proposal.fsm_state,
            mandatory_remaining=result.proposal.mandatory_remaining,
        )
        validated = Validator.validate(proposal)
        if not validated.allowed or not validated.speech:
            if self._hangup_after_playback:
                await self._maybe_hangup_when_idle()
            return
        if self._render_generation != render_generation:
            return
        await self._speak_phrase(validated.speech, render_generation)

    async def _interrupt_playback(self, *, flush: bool) -> None:
        if flush:
            asyncio.create_task(self.media.flush())
        self._render_generation = None
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
        self._tts_resamplers = {
            k: v for k, v in self._tts_resamplers.items() if not k.startswith(gen)
        }

    async def _speak_phrase(self, text: str, render_generation: str) -> None:
        if (
            not text
            or not self._playback
            or self._stopped
            or self._transport_closed
            or self._render_generation != render_generation
        ):
            return
        generation_id = f"g-{uuid.uuid4().hex[:8]}"
        phrase_id = f"p-{uuid.uuid4().hex[:8]}"
        self._active_generation = generation_id
        self._playback.begin_phrase(generation_id, phrase_id, text)
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
            except Exception:
                outcome = "failed"
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
        await self.media.emit(
            RuntimeEvent(
                self.call_id,
                RuntimeEventType.RENDERER_PHRASE_READY,
                {"phrase_id": phrase_id, "text": text, "generation_id": generation_id},
            )
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
            if self.session.state.pending_question:
                self.session.state.pending_question_delivered = True
        finish = self.media.finish or self.media.flush
        await finish()
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
) -> CallActor:
    session = CallSession(
        call_id=call_id,
        family_id=family_id,
        elder_display_name=elder_name,
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
    return CallActor(
        call_id=call_id,
        family_id=family_id,
        session=session,
        stt=HttpSTTProvider(stt_url),
        tts=HttpTTSProvider(tts_url),
        llm=HttpLLMProvider(llm_url),
        media=media,
        config=CallActorConfig(
            target_sample_rate=profile_audio["internal_sample_rate"],
            frame_ms=profile_audio["frame_ms"],
            playback_buffer_ms=playback_buffer_ms,
            telephony_stream=os.environ.get("IMVERA_TELEPHONY_STREAM", "1") == "1",
        ),
    )
