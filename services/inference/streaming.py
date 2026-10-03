"""Bounded model-thread → async HTTP bridge; completion belongs to the job."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from services.inference.common import InferenceExecutor, check_deadline


class StreamCancelled(Exception):
    """The consumer no longer needs this inference stream."""


class _OutputQueue(queue.Queue):
    def __init__(self, owner: BoundedInferenceStream, maxsize: int, max_bytes: int) -> None:
        super().__init__(maxsize=maxsize)
        self.owner = owner
        self._max_bytes = max_bytes
        self._queued_bytes = 0

    @staticmethod
    def _weight(item: Any) -> int:
        if item is None:
            return 0
        return len(json.dumps(item, ensure_ascii=False).encode("utf-8"))

    @property
    def queued_bytes(self) -> int:
        with self.mutex:
            return self._queued_bytes

    def _put(self, item: Any) -> None:
        size = self._weight(item)
        self._queued_bytes += size
        super()._put((item, size))

    def _get(self) -> Any:
        item, size = super()._get()
        self._queued_bytes -= size
        return item

    def put(self, item: Any, block: bool = True, timeout: float | None = None) -> None:
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be non-negative")
        expires = None if timeout is None else time.monotonic() + timeout
        size = self._weight(item)
        if size > self._max_bytes:
            raise ValueError("inference output chunk exceeds byte budget")
        with self.not_full:
            self.owner.check_active()
            while self._qsize() >= self.maxsize or self._queued_bytes + size > self._max_bytes:
                if not block or (expires is not None and time.monotonic() >= expires):
                    raise queue.Full
                remaining = (
                    0.05 if expires is None else min(0.05, max(0, expires - time.monotonic()))
                )
                self.not_full.wait(remaining)
                self.owner.check_active()
            self._put(item)
            self.unfinished_tasks += 1
            self.not_empty.notify()
        self.owner.notify()


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
        max_bytes: int = 2 * 1024 * 1024,
        on_close: Callable[[], None] = lambda: None,
        on_settled: Callable[[], None] = lambda: None,
    ) -> None:
        if max_chunks <= 0 or max_bytes <= 0:
            raise ValueError("stream budgets must be positive")
        self._loop = asyncio.get_running_loop()
        self._available = asyncio.Event()
        self._closed = threading.Event()
        self._cancelled = cancelled
        self._deadline = deadline
        self._on_close = on_close
        self._on_settled = on_settled
        self._settled_lock = threading.Lock()
        self._settled_called = False
        self.output = _OutputQueue(self, max_chunks, max_bytes)
        self.check_active()
        self.future = executor.submit(lambda: self._produce(produce))
        self.future.add_done_callback(lambda _: self._producer_finished())

    def _producer_finished(self) -> None:
        self.notify()
        self._release_if_settled()

    def _release_if_settled(self) -> None:
        with self._settled_lock:
            if self._settled_called or not self._closed.is_set() or not self.future.done():
                return
            self._settled_called = True
        self._on_settled()

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
            self._on_close()

    def close(self) -> None:
        self._closed.set()
        self._on_close()
        self.future.cancel()  # Only queued work can actually be cancelled.
        self._release_if_settled()

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
