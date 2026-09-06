"""Playback queue with generation-scoped cancellation."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

from packages.voice_runtime.audio import AudioEnvelope


class PlaybackState(StrEnum):
    IDLE = "idle"
    PLAYING = "playing"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"


@dataclass
class PlaybackLedger:
    phrase_id: str
    generation_id: str
    canonical_text: str
    generated_samples: int = 0
    queued_samples: int = 0
    sent_samples: int = 0
    reported_samples: int = 0
    interrupted: bool = False
    state: PlaybackState = PlaybackState.IDLE


@dataclass
class PlaybackQueue:
    call_id: str
    buffer_limit_ms: int = 200
    sample_rate: int = 16000
    _active_generation: str | None = None
    _queue: deque[AudioEnvelope] = field(default_factory=deque)
    _ledger: PlaybackLedger | None = None
    _cancelled_generations: set[str] = field(default_factory=set)

    def begin_phrase(self, generation_id: str, phrase_id: str, canonical_text: str) -> None:
        self._active_generation = generation_id
        self._ledger = PlaybackLedger(
            phrase_id=phrase_id,
            generation_id=generation_id,
            canonical_text=canonical_text,
            state=PlaybackState.PLAYING,
        )
        self._queue.clear()

    def cancel_generation(self, generation_id: str) -> None:
        self._cancelled_generations.add(generation_id)
        if self._active_generation == generation_id:
            if self._ledger:
                self._ledger.interrupted = True
                self._ledger.state = PlaybackState.INTERRUPTED
            self._queue.clear()
            self._active_generation = None

    def enqueue(self, chunk: AudioEnvelope) -> bool:
        if chunk.generation_id in self._cancelled_generations:
            return False
        if self._active_generation and chunk.generation_id != self._active_generation:
            return False
        samples = len(chunk.pcm_s16le) // 2
        if self._ledger:
            self._ledger.queued_samples += samples
        max_samples = self.sample_rate * self.buffer_limit_ms // 1000
        queued = sum(len(c.pcm_s16le) // 2 for c in self._queue)
        if queued + samples > max_samples:
            return False
        self._queue.append(chunk)
        return True

    def pop(self) -> AudioEnvelope | None:
        if not self._queue:
            return None
        chunk = self._queue.popleft()
        if self._ledger:
            self._ledger.sent_samples += len(chunk.pcm_s16le) // 2
        return chunk

    async def drain_to(self, send_fn) -> None:
        while self._queue:
            chunk = self.pop()
            if chunk is None:
                break
            await send_fn(chunk)
            await asyncio.sleep(0)

    def mark_completed(self) -> None:
        if self._ledger and not self._ledger.interrupted:
            self._ledger.state = PlaybackState.COMPLETED
