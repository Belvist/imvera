"""Playback queue — bounded wait, no sample loss."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum

from packages.voice_runtime.audio import AudioEnvelope, pcm16_frame_bytes


class PlaybackState(StrEnum):
    IDLE = "idle"
    PLAYING = "playing"
    GENERATING = "generating"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PlaybackLedger:
    phrase_id: str
    generation_id: str
    canonical_text: str
    generated_samples: int = 0
    queued_samples: int = 0
    sent_samples: int = 0
    generation_done: bool = False
    generation_outcome: str | None = None
    interrupted: bool = False
    state: PlaybackState = PlaybackState.IDLE


def split_pcm_frames(pcm_s16le: bytes, sample_rate: int, frame_ms: int = 20) -> list[bytes]:
    """Split PCM into full 20ms frames only (no trailing partial)."""
    frame_bytes = pcm16_frame_bytes(sample_rate, frame_ms)
    frames: list[bytes] = []
    offset = 0
    while offset + frame_bytes <= len(pcm_s16le):
        frames.append(pcm_s16le[offset : offset + frame_bytes])
        offset += frame_bytes
    return frames


@dataclass
class PlaybackQueue:
    call_id: str
    buffer_limit_ms: int = 800
    sample_rate: int = 16000
    frame_ms: int = 20
    _active_generation: str | None = None
    _ledger: PlaybackLedger | None = None
    _cancelled_generations: set[str] = field(default_factory=set)
    _queue: asyncio.Queue[AudioEnvelope] = field(default_factory=asyncio.Queue)
    _max_frames: int = 0
    _frame_carry: bytearray = field(default_factory=bytearray)

    def __post_init__(self) -> None:
        frames_in_buffer = max(1, self.buffer_limit_ms // self.frame_ms)
        self._max_frames = frames_in_buffer
        self._queue = asyncio.Queue(maxsize=frames_in_buffer)

    def begin_phrase(self, generation_id: str, phrase_id: str, canonical_text: str) -> None:
        self._active_generation = generation_id
        self._frame_carry.clear()
        self._ledger = PlaybackLedger(
            phrase_id=phrase_id,
            generation_id=generation_id,
            canonical_text=canonical_text,
            state=PlaybackState.GENERATING,
        )
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def cancel_generation(self, generation_id: str) -> None:
        self._cancelled_generations.add(generation_id)
        if self._active_generation == generation_id:
            if self._ledger:
                self._ledger.interrupted = True
                self._ledger.state = PlaybackState.INTERRUPTED
            self._frame_carry.clear()
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self._active_generation = None

    async def _put_frame(self, env: AudioEnvelope) -> bool:
        loop = asyncio.get_running_loop()
        frame_samples = len(env.pcm_s16le) // 2
        deadline = loop.time() + 5.0
        while True:
            if env.generation_id in self._cancelled_generations:
                return False
            try:
                self._queue.put_nowait(env)
                break
            except asyncio.QueueFull:
                if loop.time() >= deadline:
                    if self._ledger:
                        self._ledger.state = PlaybackState.FAILED
                        self._ledger.generation_outcome = "failed"
                    return False
                await asyncio.sleep(0.01)
        if self._ledger:
            self._ledger.queued_samples += frame_samples
        return True

    async def enqueue_wait(self, chunk: AudioEnvelope) -> bool:
        if chunk.generation_id in self._cancelled_generations:
            return False
        if self._active_generation and chunk.generation_id != self._active_generation:
            return False
        samples = len(chunk.pcm_s16le) // 2
        if self._ledger:
            self._ledger.generated_samples += samples
            self._ledger.state = PlaybackState.PLAYING
        self._frame_carry.extend(chunk.pcm_s16le)
        frame_bytes = pcm16_frame_bytes(chunk.sample_rate, self.frame_ms)
        while len(self._frame_carry) >= frame_bytes:
            frame_pcm = bytes(self._frame_carry[:frame_bytes])
            del self._frame_carry[:frame_bytes]
            env = AudioEnvelope(
                call_id=chunk.call_id,
                generation_id=chunk.generation_id,
                phrase_id=chunk.phrase_id,
                sequence=chunk.sequence,
                sample_rate=chunk.sample_rate,
                pcm_s16le=frame_pcm,
            )
            if not await self._put_frame(env):
                return False
        return True

    async def flush_carried_frames(self, chunk: AudioEnvelope) -> bool:
        """Pad and enqueue one final frame when TTS generation ends."""
        if chunk.generation_id in self._cancelled_generations:
            return False
        if not self._frame_carry:
            return True
        frame_bytes = pcm16_frame_bytes(chunk.sample_rate, self.frame_ms)
        pad = frame_bytes - len(self._frame_carry)
        if pad > 0:
            self._frame_carry.extend(b"\x00" * pad)
        frame_pcm = bytes(self._frame_carry[:frame_bytes])
        self._frame_carry.clear()
        env = AudioEnvelope(
            call_id=chunk.call_id,
            generation_id=chunk.generation_id,
            phrase_id=chunk.phrase_id,
            sequence=chunk.sequence,
            sample_rate=chunk.sample_rate,
            pcm_s16le=frame_pcm,
        )
        return await self._put_frame(env)

    def pop_nowait(self) -> AudioEnvelope | None:
        try:
            chunk = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
        if self._ledger:
            self._ledger.sent_samples += len(chunk.pcm_s16le) // 2
        return chunk

    def mark_generation_done(self, outcome: str = "success") -> None:
        if self._ledger:
            self._ledger.generation_done = True
            self._ledger.generation_outcome = outcome
            if outcome == "success":
                self._ledger.state = PlaybackState.PLAYING
            elif outcome == "cancelled":
                self._ledger.state = PlaybackState.CANCELLED
            else:
                self._ledger.state = PlaybackState.FAILED

    def playback_complete(self) -> bool:
        if not self._ledger or self._ledger.interrupted:
            return False
        if self._ledger.generation_outcome not in (None, "success"):
            return False
        return self._ledger.generation_done and self._queue.empty()

    def mark_completed(self) -> None:
        if self._ledger and not self._ledger.interrupted and self._ledger.sent_samples > 0:
            self._ledger.state = PlaybackState.COMPLETED

    @property
    def pending_frames(self) -> int:
        return self._queue.qsize()
