"""Per-call voice actor — event queue, revision guards, no blocking on inference."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from packages.contracts.interpretation import TurnInterpretation
from packages.contracts.providers import STTProvider, TTSProvider
from packages.contracts.runtime import RuntimeEvent, RuntimeEventType
from packages.dialogue.context_builder import build_turn_context
from packages.dialogue.interpretation import to_turn_interpretation
from packages.dialogue.semantic_bridge import semantic_to_user_interpretation
from packages.dialogue.session import CallSession
from packages.voice_runtime.audio import AudioEnvelope, StatefulResampler
from packages.voice_runtime.endpointing import SpeechSegmentCollector
from packages.voice_runtime.playback import PlaybackQueue
from packages.voice_runtime.vad import EnergyVad
from services.llm.http_provider import HttpLLMProvider
from services.stt.http_provider import HttpSTTProvider
from services.tts.http_provider import HttpTTSProvider

SendAudioFn = Callable[[AudioEnvelope], Awaitable[None]]
EmitFn = Callable[[RuntimeEvent], Awaitable[None]]


class ActorEventType(StrEnum):
    PCM = "pcm"
    SPEECH_STARTED = "speech_started"
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
    playback_buffer_ms: int = 200


@dataclass
class CallActor:
    call_id: str
    family_id: str
    session: CallSession
    stt: STTProvider
    tts: TTSProvider
    llm: HttpLLMProvider
    send_audio: SendAudioFn
    emit: EmitFn
    config: CallActorConfig = field(default_factory=CallActorConfig)
    _queue: asyncio.Queue[ActorEvent] = field(default_factory=asyncio.Queue)
    _task: asyncio.Task | None = None
    _policy_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _resampler: StatefulResampler | None = None
    _vad: EnergyVad | None = None
    _collector: SpeechSegmentCollector | None = None
    _playback: PlaybackQueue | None = None
    _active_generation: str | None = None
    _tts_task: asyncio.Task | None = None
    _utterance_seq: int = 0
    _state_version_at_work: int = 0
    _delivered_phrases: list[str] = field(default_factory=list)

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        await self._queue.put(ActorEvent(ActorEventType.STOP))
        if self._task:
            await self._task

    async def push_pcm(self, pcm: bytes, sample_rate: int) -> None:
        await self._queue.put(ActorEvent(ActorEventType.PCM, pcm=pcm, sample_rate=sample_rate))

    async def _run(self) -> None:
        result = await asyncio.to_thread(self.session.start)
        await self.emit(RuntimeEvent(self.call_id, RuntimeEventType.CALL_STARTED, {}))
        if result.validated.allowed and result.validated.speech:
            self._delivered_phrases.append(result.validated.speech)
            await self._speak_phrase(result.validated.speech)
        while True:
            event = await self._queue.get()
            if event.kind == ActorEventType.STOP:
                await self._interrupt_playback()
                await self.emit(
                    RuntimeEvent(self.call_id, RuntimeEventType.TRANSPORT_DISCONNECTED, {})
                )
                break
            if event.kind == ActorEventType.PCM:
                await self._on_pcm(event.pcm, event.sample_rate)

    async def _ensure_audio_chain(self, sample_rate: int) -> None:
        if self._resampler is None:
            self._resampler = StatefulResampler(sample_rate, self.config.target_sample_rate)
            self._vad = EnergyVad(self.config.target_sample_rate)
            self._collector = SpeechSegmentCollector(self.config.target_sample_rate)
            self._playback = PlaybackQueue(
                self.call_id,
                buffer_limit_ms=self.config.playback_buffer_ms,
                sample_rate=self.config.target_sample_rate,
            )
            await self.emit(
                RuntimeEvent(
                    self.call_id,
                    RuntimeEventType.MEDIA_READY,
                    {"sample_rate": sample_rate},
                )
            )

    async def _on_pcm(self, pcm_s16le: bytes, sample_rate: int) -> None:
        await self._ensure_audio_chain(sample_rate)
        assert self._resampler and self._vad and self._collector
        pcm = self._resampler.process(pcm_s16le)
        if not pcm:
            return
        started, ended = self._vad.feed(pcm)
        if started:
            await self._interrupt_playback()
            await self.emit(RuntimeEvent(self.call_id, RuntimeEventType.SPEECH_STARTED, {}))
        segment = self._collector.on_frame(pcm, started, ended)
        if segment:
            await self.emit(RuntimeEvent(self.call_id, RuntimeEventType.SPEECH_ENDED, {}))
            asyncio.create_task(self._handle_utterance(segment))

    async def _handle_utterance(self, pcm: bytes) -> None:
        self._utterance_seq += 1
        utterance_id = f"u-{self._utterance_seq}"
        turn_id = self.session.turn_id + 1
        captured_version = self.session.state.state_version
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
            await self.emit(
                RuntimeEvent(
                    self.call_id,
                    RuntimeEventType.INTERPRETATION_FAILED,
                    {"error": str(exc), "stage": "stt"},
                )
            )
            return
        text = (stt_result.text or "").strip()
        await self.emit(
            RuntimeEvent(
                self.call_id,
                RuntimeEventType.STT_FINAL,
                {"utterance_id": utterance_id, "text": text},
            )
        )
        if not text:
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
            await self.emit(
                RuntimeEvent(
                    self.call_id,
                    RuntimeEventType.INTERPRETATION_FAILED,
                    {"error": str(exc), "stage": "llm"},
                )
            )
            return
        await self.emit(RuntimeEvent(self.call_id, RuntimeEventType.INTERPRETATION_READY, {}))
        interp = semantic_to_user_interpretation(text, semantic.payload)
        legacy_contract: TurnInterpretation = to_turn_interpretation(
            self.session.state,
            turn_id,
            text,
            interp,
            state_version=captured_version,
            asr_quality=stt_result.asr_quality,
        )

        async with self._policy_lock:
            if self.session.state.state_version != captured_version:
                return
            result = await asyncio.to_thread(
                self.session.handle_user_text,
                text,
                interp=interp,
                contract=legacy_contract,
            )

        if not result.persist_ok:
            await self.emit(
                RuntimeEvent(
                    self.call_id,
                    RuntimeEventType.PERSISTENCE_FAILED,
                    {"error": result.persist_error},
                )
            )
            return
        await self.emit(RuntimeEvent(self.call_id, RuntimeEventType.PERSISTENCE_COMMITTED, {}))
        if result.validated.allowed and result.validated.speech:
            self._delivered_phrases.append(result.validated.speech)
            await self._speak_phrase(result.validated.speech)
        elif self.session.state.call_finalized:
            await self.emit(RuntimeEvent(self.call_id, RuntimeEventType.CALL_STOP_REQUESTED, {}))

    async def _interrupt_playback(self) -> None:
        if not self._playback or not self._active_generation:
            return
        gen = self._active_generation
        self._playback.cancel_generation(gen)
        await self.tts.cancel(gen)
        if self._tts_task and not self._tts_task.done():
            self._tts_task.cancel()
        await self.emit(
            RuntimeEvent(
                self.call_id,
                RuntimeEventType.PLAYBACK_INTERRUPTED,
                {"generation_id": gen},
            )
        )
        self._active_generation = None

    async def _speak_phrase(self, text: str) -> None:
        if not text or not self._playback:
            return
        generation_id = f"g-{uuid.uuid4().hex[:8]}"
        phrase_id = f"p-{uuid.uuid4().hex[:8]}"
        self._active_generation = generation_id
        self._playback.begin_phrase(generation_id, phrase_id, text)
        deadline = time.monotonic() + self.config.tts_deadline_s
        seq = 0

        async def _run_tts() -> None:
            nonlocal seq
            async for chunk in self.tts.synthesize(
                text,
                generation_id=generation_id,
                phrase_id=phrase_id,
                deadline=deadline,
            ):
                if generation_id != self._active_generation:
                    break
                env = AudioEnvelope(
                    call_id=self.call_id,
                    generation_id=generation_id,
                    phrase_id=phrase_id,
                    sequence=seq,
                    sample_rate=chunk.sample_rate,
                    pcm_s16le=chunk.pcm_s16le,
                )
                seq += 1
                if self._playback.enqueue(env):
                    await self.send_audio(env)
            if generation_id == self._active_generation:
                self._playback.mark_completed()
                await self.emit(
                    RuntimeEvent(
                        self.call_id,
                        RuntimeEventType.PLAYBACK_COMPLETED,
                        {"generation_id": generation_id},
                    )
                )

        self._tts_task = asyncio.create_task(_run_tts())
        await self.emit(
            RuntimeEvent(
                self.call_id,
                RuntimeEventType.RENDERER_PHRASE_READY,
                {"phrase_id": phrase_id, "text": text},
            )
        )


def build_call_actor(
    call_id: str,
    family_id: str,
    elder_name: str,
    stt_url: str,
    tts_url: str,
    llm_url: str,
    send_audio: SendAudioFn,
    emit: EmitFn,
) -> CallActor:
    session = CallSession(
        call_id=call_id,
        family_id=family_id,
        elder_display_name=elder_name,
    )
    return CallActor(
        call_id=call_id,
        family_id=family_id,
        session=session,
        stt=HttpSTTProvider(stt_url),
        tts=HttpTTSProvider(tts_url),
        llm=HttpLLMProvider(llm_url),
        send_audio=send_audio,
        emit=emit,
    )
