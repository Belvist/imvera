"""Bounded model-thread → async HTTP bridge; completion belongs to the job."""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from services.inference.common import InferenceExecutor, check_deadline


class StreamCancelled(Exception):
    """The consumer no longer needs this inference stream."""


class _OutputQueue(queue.Queue):
    def __init__(self, owner: BoundedInferenceStream, maxsize: int) -> None:
        super().__init__(maxsize=maxsize)
        self.owner = owner

    def put(self, item: Any, block: bool = True, timeout: float | None = None) -> None:
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be non-negative")
        expires = None if timeout is None else time.monotonic() + timeout
        while True:
            self.owner.check_active()
            try:
                if not block:
                    super().put(item, block=False)
                else:
                    remaining = (
                        0.05 if expires is None else min(0.05, max(0, expires - time.monotonic()))
                    )
                    super().put(item, timeout=remaining)
                self.owner.notify()
                return
            except queue.Full:
                if not block or (expires is not None and time.monotonic() >= expires):
                    raise


class BoundedInferenceStream:
    """One existing executor job, finite output, and no blocking reader thread.

    Admission is synchronous, before streaming response headers. Disconnects
    stop queue writes and cancel queued work; running kernels retain executor
    capacity until they actually return. Producer completion, not a sentinel,
    proves success (a producer can fail after emitting its final sentinel).
    """

    def __init__(
        self,
        executor: InferenceExecutor,
        produce: Callable[[queue.Queue], None],
        *,
        deadline: float | None = None,
        cancelled: Callable[[], bool] = lambda: False,
        max_chunks: int = 8,
    ) -> None:
        if max_chunks <= 0:
            raise ValueError("max_chunks must be positive")
        self._loop = asyncio.get_running_loop()
        self._available = asyncio.Event()
        self._closed = threading.Event()
        self._cancelled = cancelled
        self._deadline = deadline
        self.output = _OutputQueue(self, max_chunks)
        self.check_active()
        self.future = executor.submit(lambda: self._produce(produce))
        self.future.add_done_callback(lambda _: self.notify())

    def _produce(self, produce: Callable[[queue.Queue], None]) -> None:
        self.check_active()
        produce(self.output)

    def check_active(self) -> None:
        if self._closed.is_set() or self._cancelled():
            raise StreamCancelled()
        check_deadline(self._deadline)

    def notify(self) -> None:
        try:
            self._loop.call_soon_threadsafe(self._available.set)
        except RuntimeError:
            # A closed HTTP loop cannot receive PCM or own model completion.
            self._closed.set()

    def close(self) -> None:
        self._closed.set()
        self.future.cancel()  # Only queued work can actually be cancelled.

    async def items(self) -> AsyncIterator[Any]:
        try:
            while True:
                self.check_active()
                self._available.clear()
                try:
                    item = self.output.get_nowait()
                except queue.Empty:
                    if self.future.done():
                        self.future.result()
                        return
                    try:
                        await asyncio.wait_for(self._available.wait(), timeout=0.05)
                    except TimeoutError:
                        continue  # Recheck deadline/explicit cancel even without PCM.
                else:
                    if item is not None:
                        yield item
        finally:
            self.close()
