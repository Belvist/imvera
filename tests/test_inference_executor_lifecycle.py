"""Inference admission must recover from queued cancellation and shutdown."""

import asyncio
import threading
import time

import pytest

from services.inference.common import InferenceExecutor, QueueFullError


def test_cancelled_queued_future_releases_capacity_without_running_model():
    ex = InferenceExecutor(max_queue=2)
    gate = threading.Event()
    calls = []
    running = ex.submit(lambda: gate.wait(3))
    try:
        queued = ex.submit(lambda: calls.append("cancelled model"))
        assert ex.queue_depth == 2
        assert queued.cancel()
        assert ex.queue_depth == 1
        replacement = ex.submit(lambda: "next model result")
        with pytest.raises(QueueFullError):
            ex.submit(lambda: None)
        gate.set()
        running.result(timeout=2)
        assert replacement.result(timeout=2) == "next model result"
        assert not calls and ex.queue_depth == 0
    finally:
        gate.set()
        ex._executor.shutdown(wait=True)


def test_submission_failure_does_not_leave_phantom_queue_depth():
    ex = InferenceExecutor(max_queue=2)
    ex._executor.shutdown(wait=True)
    with pytest.raises(RuntimeError, match="shutdown"):
        ex.submit(lambda: None)
    assert ex.queue_depth == 0


def test_async_cancel_preserves_job_cleanup_and_does_not_use_default_thread_pool():
    async def scenario():
        ex = InferenceExecutor(max_queue=2)
        gate = threading.Event()
        abandoned = threading.Event()
        cleaned = threading.Event()

        def infer():
            try:
                assert gate.wait(3)
                assert abandoned.is_set()
                raise RuntimeError("abandoned model output")
            finally:
                cleaned.set()

        async def worker_request():
            try:
                return await ex.run(infer)
            finally:
                abandoned.set()

        task = asyncio.create_task(worker_request())
        try:
            deadline = time.monotonic() + 2
            while ex.queue_depth != 1:
                assert time.monotonic() < deadline
                await asyncio.sleep(0)
            assert asyncio.get_running_loop()._default_executor is None
            task.cancel()
            result = (await asyncio.gather(task, return_exceptions=True))[0]
            assert isinstance(result, asyncio.CancelledError) and abandoned.is_set()
            assert ex.queue_depth == 1, "cancelled caller cannot claim running model stopped"
            gate.set()
            while not cleaned.is_set() or ex.queue_depth:
                assert time.monotonic() < deadline
                await asyncio.sleep(0.002)
            assert await ex.run(lambda: "recovered") == "recovered"
        finally:
            gate.set()
            await asyncio.gather(task, return_exceptions=True)
            ex._executor.shutdown(wait=True)

    asyncio.run(scenario())
