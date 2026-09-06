"""VoiceRuntime — one actor per call_id; no blocking in event handler."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from packages.contracts.providers import STTProvider, TTSProvider
from packages.contracts.runtime import RuntimeEvent, RuntimeEventType
from packages.dialogue.session import CallSession
from packages.voice_runtime.audio import AudioEnvelope, StatefulResampler
from packages.voice_runtime.endpointing import SpeechSegmentCollector
from packages.voice_runtime.playback import PlaybackQueue
from packages.voice_runtime.vad import EnergyVad

SendAudioFn = Callable[[AudioEnvelope], Awaitable[None]]
EmitFn = Callable[[RuntimeEvent], Awaitable[None]]


@dataclass
class VoiceRuntimeConfig:
    target_sample_rate: int = 16000
    playback_buffer_ms: int = 200
    stt_deadline_s: float = 8.0
    tts_deadline_s: float = 12.0


@dataclass
class VoiceRuntime:
    call_id: str
    family_id: str
    session: CallSession
    stt: STTProvider
    tts: TTSProvider
    send_audio: SendAudioFn
    emit: EmitFn
    config: VoiceRuntimeConfig = field(default_factory=VoiceRuntimeConfig)
    _started: bool = False
    _media_ready: bool = False
    _resampler: StatefulResampler | None = None
    _vad: EnergyVad | None = None
    _collector: SpeechSegmentCollector | None = None
    _playback: PlaybackQueue | None = None
    _active_generation: str | None = None
    _stt_task: asyncio.Task | None = None
    _tts_task: asyncio.Task | None = None
    _input_rate: int = 16000

    async def handle_media_ready(self, sample_rate: int) -> None:
        self._input_rate = sample_rate
        self._resampler = StatefulResampler(sample_rate, self.config.target_sample_rate)
        self._vad = EnergyVad(self.config.target_sample_rate)
        self._collector = SpeechSegmentCollector(self.config.target_sample_rate)
        self._playback = PlaybackQueue(
            self.call_id,
            buffer_limit_ms=self.config.playback_buffer_ms,
            sample_rate=self.config.target_sample_rate,
        )
        self._media_ready = True
        await self.emit(
            RuntimeEvent(self.call_id, RuntimeEventType.MEDIA_READY, {"sample_rate": sample_rate})
        )

    async def start_call(self) -> None:
        if self._started:
            return
        self._started = True
        result = await asyncio.to_thread(self.session.start)
        await self.emit(RuntimeEvent(self.call_id, RuntimeEventType.CALL_STARTED, {}))
        if result.validated.allowed and result.validated.speech:
            await self._speak_phrase(result.validated.speech)

    async def _speak_opening(self) -> None:
        pass

    async def on_pcm(self, pcm_s16le: bytes, sample_rate: int) -> None:
        if not self._media_ready:
            await self.handle_media_ready(sample_rate)
        assert self._resampler and self._vad and self._collector and self._playback
        pcm = self._resampler.process(pcm_s16le)
        if not pcm:
            return
        started, ended = self._vad.feed(pcm)
        if started and self._active_generation:
            await self._interrupt_playback()
        if started:
            await self.emit(RuntimeEvent(self.call_id, RuntimeEventType.SPEECH_STARTED, {}))
        segment = self._collector.on_frame(pcm, started, ended)
        if segment:
            await self.emit(RuntimeEvent(self.call_id, RuntimeEventType.SPEECH_ENDED, {}))
            await self._on_utterance(segment)

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

    async def _on_utterance(self, pcm: bytes) -> None:
        if self._stt_task and not self._stt_task.done():
            return
        utterance_id = f"u-{uuid.uuid4().hex[:12]}"
        turn_id = self.session.turn_id + 1
        deadline = time.monotonic() + self.config.stt_deadline_s
        self._stt_task = asyncio.create_task(
            self._process_utterance(pcm, utterance_id, turn_id, deadline)
        )

    async def _process_utterance(
        self, pcm: bytes, utterance_id: str, turn_id: int, deadline: float
    ) -> None:
        try:
            stt_result = await self.stt.transcribe_final(
                pcm,
                self.config.target_sample_rate,
                call_id=self.call_id,
                turn_id=turn_id,
                deadline=deadline,
            )
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
            result = await asyncio.to_thread(self.session.handle_user_text, text)
            if not result.persist_ok:
                await self.emit(
                    RuntimeEvent(
                        self.call_id,
                        RuntimeEventType.PERSISTENCE_FAILED,
                        {"error": result.persist_error},
                    )
                )
                return
            await self.emit(
                RuntimeEvent(self.call_id, RuntimeEventType.PERSISTENCE_COMMITTED, {})
            )
            if result.validated.allowed and result.validated.speech:
                await self._speak_phrase(result.validated.speech)
            elif self.session.state.call_finalized:
                await self.emit(
                    RuntimeEvent(self.call_id, RuntimeEventType.CALL_STOP_REQUESTED, {})
                )
        except Exception as exc:
            await self.emit(
                RuntimeEvent(
                    self.call_id,
                    RuntimeEventType.INTERPRETATION_FAILED,
                    {"error": str(exc)},
                )
            )

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
                    await self.emit(
                        RuntimeEvent(
                            self.call_id,
                            RuntimeEventType.TTS_CHUNK_READY,
                            {"sequence": seq},
                        )
                    )
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

    async def stop(self) -> None:
        if self._active_generation:
            await self._interrupt_playback()
        await self.emit(RuntimeEvent(self.call_id, RuntimeEventType.TRANSPORT_DISCONNECTED, {}))
