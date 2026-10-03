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
    runtime_metadata: dict[str, str] = field(default_factory=dict)


def new_request_id() -> str:
    return f"req-{uuid.uuid4().hex[:12]}"


class QueueFullError(RuntimeError):
    """Inference executor saturated."""


class InferenceExecutor:
    """Single-thread executor for MLX model access."""

    def __init__(self, max_queue: int = 4) -> None:
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._max_queue = max_queue
        self._pending = 0
        self._lock = threading.Lock()
        self._stopping = False
        self._running_since: float | None = None

    @property
    def running_age_s(self) -> float:
        with self._lock:
            return 0 if self._running_since is None else time.monotonic() - self._running_since

    def shutdown(self) -> None:
        """Stop admission/cancel queued work; running jobs retain their lifetime."""
        with self._lock:
            self._stopping = True
        self._executor.shutdown(wait=False, cancel_futures=True)

    @property
    def queue_depth(self) -> int:
        with self._lock:
            return self._pending

    def submit(
        self,
        fn: Callable[[], T],
        *,
        idle_only: bool = False,
    ) -> concurrent.futures.Future[T]:
        with self._lock:
            if self._stopping:
                raise QueueFullError("inference worker draining")
            if idle_only and self._pending:
                raise QueueFullError("inference worker busy; preview not admitted")
            if self._pending >= self._max_queue:
                raise QueueFullError("inference queue full")
            self._pending += 1

        def finished(_future: concurrent.futures.Future[T]) -> None:
            with self._lock:
                self._pending -= 1

        try:

            def run_job() -> T:
                with self._lock:
                    self._running_since = time.monotonic()
                try:
                    return fn()
                finally:
                    with self._lock:
                        self._running_since = None

            future = self._executor.submit(run_job)
        except BaseException:
            with self._lock:
                self._pending -= 1
            raise
        # Counts cancelled queued work too: its function never runs, so a
        # decrement inside fn/finally would permanently consume queue capacity.
        future.add_done_callback(finished)
        return future

    async def run(self, fn: Callable[[], T], *, idle_only: bool = False) -> T:
        fut = self.submit(fn, idle_only=idle_only)
        wrapped = asyncio.wrap_future(fut)
        try:
            # The job owns its input/resources. Caller cancellation marks it
            # abandoned in the worker; do not cancel queued resource cleanup.
            # Await the Future directly, without a second blocked pool thread.
            return await asyncio.shield(wrapped)
        except asyncio.CancelledError:

            def consume_result(done: asyncio.Future) -> None:
                if not done.cancelled():
                    done.exception()

            wrapped.add_done_callback(consume_result)
            raise


def mount_health(
    app: FastAPI,
    state: WorkerState,
    service: str,
    executor: InferenceExecutor | None = None,
    *,
    executor_supplier: Callable[[], InferenceExecutor | None] | None = None,
    details_supplier: Callable[[], dict] | None = None,
    readiness_check: Callable[[], bool] | None = None,
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
        details = details_supplier() if details_supplier is not None else {}
        details["runtime"] = dict(state.runtime_metadata)
        dependency_ready = (
            readiness_check() if state.ready and readiness_check is not None else True
        )
        if state.ready and dependency_ready:
            return JSONResponse(
                {
                    "status": "ready",
                    "service": service,
                    "model_revision": state.model_revision,
                    "queue_depth": _queue_depth(),
                    **details,
                }
            )
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "service": service,
                "error": state.warmup_error or "warming up",
                "queue_depth": _queue_depth(),
                **details,
            },
        )


def check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() > deadline:
        raise TimeoutError("deadline exceeded")


def executor_http_error(exc: Exception) -> Exception:
    """Map executor saturation to retryable HTTP codes (never 500).

    429 = try another replica now; 503 = server overloaded/slow.
    Both are in the providers' retryable set; model verdicts never land here.
    """
    from fastapi import HTTPException

    if isinstance(exc, QueueFullError):
        return HTTPException(status_code=429, detail="inference queue full")
    if isinstance(exc, TimeoutError):
        return HTTPException(status_code=503, detail="deadline exceeded")
    return exc
