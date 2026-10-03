"""Dedicated model-process containment; never applied to SDK/state writers."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from services.inference.common import InferenceExecutor, WorkerState
from services.inference.config import production_mode


class InferenceWatchdog:
    def __init__(
        self,
        executor: InferenceExecutor,
        state: WorkerState,
        *,
        max_job_s: float,
        fatal: Callable[[], None] = lambda: os._exit(70),
        poll_s: float = 0.5,
    ) -> None:
        if max_job_s <= 0 or poll_s <= 0:
            raise ValueError("watchdog limits must be positive")
        self._stop = threading.Event()

        def watch() -> None:
            while not self._stop.wait(poll_s):
                if executor.running_age_s > max_job_s:
                    state.ready = False
                    state.warmup_error = "inference job exceeded process hard timeout"
                    logging.getLogger("inference.watchdog").error(state.warmup_error)
                    fatal()
                    return

        self._thread = threading.Thread(target=watch, name="inference-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1)


def production_watchdog(
    executor: InferenceExecutor,
    state: WorkerState,
    config: dict,
) -> InferenceWatchdog | None:
    if not production_mode():
        return None
    return InferenceWatchdog(
        executor,
        state,
        max_job_s=float(config.get("limits", {}).get("worker_job_hard_timeout_s", 120)),
    )


@contextmanager
def production_startup_guard(state: WorkerState, config: dict) -> Iterator[None]:
    """A hung model load has no running executor job yet; contain it too."""
    if not production_mode():
        yield
        return

    def expired() -> None:
        state.ready = False
        state.warmup_error = "model startup exceeded process hard timeout"
        logging.getLogger("inference.watchdog").error(state.warmup_error)
        os._exit(70)

    timer = threading.Timer(
        float(config.get("limits", {}).get("worker_startup_hard_timeout_s", 240)), expired
    )
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
