"""LiveKit outbound PCM pump — bounded queue → AudioSource.capture_frame."""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from packages.voice_runtime.audio import pcm_rms_s16le

if TYPE_CHECKING:
    from livekit import rtc

log = logging.getLogger(__name__)

EmitStageFn = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class LiveKitOutboundPump:
    """CallActor send_pcm → asyncio queue → LiveKit AudioSource (non-blocking hot path)."""

    sample_rate: int = 16000
    num_channels: int = 1
    frame_samples: int = 320  # 20ms @ 16kHz
    queue_max: int = 256
    _queue: asyncio.Queue[tuple[int, bytes]] = field(default_factory=asyncio.Queue)
    _generation: int = 0
    _task: asyncio.Task | None = None
    _audio_source: rtc.AudioSource | None = None
    _emit_stage: EmitStageFn | None = None
    _on_frame_sent: Callable[[int], None] | None = None
    _stopped: bool = False
    _capture_tasks: set[asyncio.Task] = field(default_factory=set)

    def bind_source(
        self,
        source: rtc.AudioSource,
        *,
        emit_stage: EmitStageFn | None = None,
        on_frame_sent: Callable[[int], None] | None = None,
    ) -> None:
        self._audio_source = source
        self._emit_stage = emit_stage
        self._on_frame_sent = on_frame_sent

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="livekit-outbound-pump")

    async def stop(self) -> None:
        self._stopped = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        for task in list(self._capture_tasks):
            task.cancel()
        if self._capture_tasks:
            await asyncio.gather(*self._capture_tasks, return_exceptions=True)
        self._capture_tasks.clear()

    def enqueue_pcm(self, pcm16le: bytes, generation: int) -> None:
        if self._stopped or not pcm16le:
            return
        if generation < self._generation:
            return
        try:
            self._queue.put_nowait((generation, pcm16le))
        except asyncio.QueueFull:
            log.warning("LiveKit outbound queue full — dropping TTS chunk")

    def bump_generation(self) -> int:
        self._generation += 1
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        return self._generation

    @property
    def generation(self) -> int:
        return self._generation

    async def clear_playback(self, source: rtc.AudioSource) -> None:
        gen = self.bump_generation()
        source.clear_queue()
        for task in list(self._capture_tasks):
            task.cancel()
        if self._capture_tasks:
            await asyncio.gather(*self._capture_tasks, return_exceptions=True)
        self._capture_tasks.clear()
        if self._emit_stage:
            await self._emit_stage("livekit.playback.cleared", generation=gen)

    async def wait_playout(self, source: rtc.AudioSource, generation: int) -> None:
        if generation < self._generation:
            return
        await source.wait_for_playout()
        if self._emit_stage:
            await self._emit_stage("livekit.playback.drained", generation=generation)

    async def _run(self) -> None:
        carry = bytearray()
        while not self._stopped:
            try:
                gen, pcm = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if gen < self._generation:
                continue
            carry.extend(pcm)
            frame_bytes = self.frame_samples * 2 * self.num_channels
            while len(carry) >= frame_bytes:
                chunk = bytes(carry[:frame_bytes])
                del carry[:frame_bytes]
                if gen < self._generation:
                    break
                await self._send_frame(chunk, gen)

    async def _send_frame(self, pcm: bytes, generation: int) -> None:
        if self._audio_source is None or generation < self._generation:
            return
        from livekit import rtc

        samples = len(pcm) // (2 * self.num_channels)
        frame = rtc.AudioFrame(
            data=pcm,
            sample_rate=self.sample_rate,
            num_channels=self.num_channels,
            samples_per_channel=samples // self.num_channels,
        )
        task = asyncio.create_task(self._capture_with_generation(frame, generation))
        self._capture_tasks.add(task)
        task.add_done_callback(self._capture_tasks.discard)

    async def _capture_with_generation(self, frame: rtc.AudioFrame, generation: int) -> None:
        if self._audio_source is None or generation < self._generation:
            return
        try:
            await self._audio_source.capture_frame(frame)
        except Exception as exc:
            log.warning("LiveKit capture_frame failed: %s", exc)
            return
        nbytes = len(frame.data)
        if self._on_frame_sent:
            self._on_frame_sent(nbytes)
        if self._emit_stage:
            rms = round(pcm_rms_s16le(bytes(frame.data)), 1)
            peak = 0
            if len(frame.data) >= 2:
                peak = max(
                    abs(int.from_bytes(frame.data[i : i + 2], "little", signed=True))
                    for i in range(0, len(frame.data) - 1, 2)
                )
            await self._emit_stage(
                "livekit.outbound.frame",
                bytes=nbytes,
                rms=rms,
                peak=peak,
                generation=generation,
            )


def pcm16le_to_audio_frame(
    pcm16le: bytes,
    *,
    sample_rate: int = 16000,
    num_channels: int = 1,
) -> rtc.AudioFrame:
    from livekit import rtc

    samples = len(pcm16le) // (2 * num_channels)
    return rtc.AudioFrame(
        data=pcm16le,
        sample_rate=sample_rate,
        num_channels=num_channels,
        samples_per_channel=samples // num_channels,
    )
