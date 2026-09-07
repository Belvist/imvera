"""Shared inference worker utilities — queues, cancel, readiness."""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

from fastapi import FastAPI
from fastapi.responses import JSONResponse

T = TypeVar("T")


@dataclass
class WorkerState:
    ready: bool = False
    warmup_error: str | None = None
    model_revision: str = ""
    queue_depth: int = 0
    cancelled_generations: set[str] = field(default_factory=set)
    cancelled_requests: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)


def new_request_id() -> str:
    return f"req-{uuid.uuid4().hex[:12]}"


class InferenceExecutor:
    """Single-thread executor for MLX model access."""

    def __init__(self, max_queue: int = 4) -> None:
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._max_queue = max_queue
        self._pending = 0
        self._lock = threading.Lock()

    @property
    def queue_depth(self) -> int:
        with self._lock:
            return self._pending

    def submit(self, fn: Callable[[], T]) -> concurrent.futures.Future[T]:
        with self._lock:
            if self._pending >= self._max_queue:
                raise RuntimeError("inference queue full")
            self._pending += 1

        def wrapped() -> T:
            try:
                return fn()
            finally:
                with self._lock:
                    self._pending -= 1

        return self._executor.submit(wrapped)

    async def run(self, fn: Callable[[], T]) -> T:
        loop = asyncio.get_running_loop()
        fut = self.submit(fn)
        return await loop.run_in_executor(None, fut.result)


def mount_health(
    app: FastAPI,
    state: WorkerState,
    service: str,
    executor: InferenceExecutor | None = None,
    *,
    executor_supplier: Callable[[], InferenceExecutor | None] | None = None,
) -> None:
    def _queue_depth() -> int:
        ex = executor_supplier() if executor_supplier is not None else executor
        if ex is not None:
            return ex.queue_depth
        return state.queue_depth

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "live", "service": service}

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        if state.ready:
            return JSONResponse(
                {
                    "status": "ready",
                    "service": service,
                    "model_revision": state.model_revision,
                    "queue_depth": _queue_depth(),
                }
            )
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "service": service,
                "error": state.warmup_error or "warming up",
            },
        )


def check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() > deadline:
        raise TimeoutError("deadline exceeded")
