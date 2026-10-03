"""Long-lived worker memory, portable configuration and fail-closed voice."""

from __future__ import annotations

import asyncio
import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from services.inference.cancellation import CancellationRegistry, DuplicateRequestError
from services.inference.common import InferenceExecutor, QueueFullError, WorkerState
from services.inference.config import load_worker_config, validate_worker_config
from services.inference.streaming import BoundedInferenceStream
from services.inference.watchdog import InferenceWatchdog
from services.stt.gigaam_engine import ensure_gigaam_artifacts
from services.tts import worker


def test_cancel_storm_is_bounded_but_does_not_revive_active_cancelled_request():
    now = [0.0]
    registry = CancellationRegistry(max_tombstones=4, ttl_s=10, clock=lambda: now[0])
    lease = registry.register("active", "generation")
    registry.cancel(request_id="active")
    for index in range(10000):
        registry.cancel(request_id=f"r-{index}", generation_id=f"g-{index}")
    assert registry.stats() == {"active": 1, "tombstones": 4}
    assert lease.cancelled.is_set()
    assert registry.is_cancelled("active", "generation")
    now[0] = 11
    assert registry.stats() == {"active": 1, "tombstones": 0}
    assert registry.is_cancelled("active", "generation")
    registry.release(lease)
    assert registry.stats() == {"active": 0, "tombstones": 0}


def test_generation_cancel_reaches_all_active_phrases_and_early_cancel():
    registry = CancellationRegistry()
    first = registry.register("r1", "g")
    second = registry.register("r2", "g")
    unrelated = registry.register("r3", "other")
    registry.cancel(generation_id="g")
    assert first.cancelled.is_set() and second.cancelled.is_set()
    assert not unrelated.cancelled.is_set()
    assert registry.register("later-phrase", "g").cancelled.is_set()
    with pytest.raises(DuplicateRequestError):
        registry.register("r1", "new-generation")


def test_release_of_old_lease_cannot_remove_reused_identity():
    registry = CancellationRegistry()
    old = registry.register("r", "g")
    registry.release(old)
    new = registry.register("r", "g2")
    registry.release(old)
    assert registry.stats()["active"] == 1
    registry.cancel(request_id="r")
    assert new.cancelled.is_set()


def test_active_streams_are_bounded_even_after_producers_finish():
    registry = CancellationRegistry(max_active_requests=2)
    first = registry.register("r1", "g1")
    registry.register("r2", "g2")
    with pytest.raises(QueueFullError, match="HTTP streams full"):
        registry.register("r3", "g3")
    registry.release(first)
    registry.register("r3", "g3")
    assert registry.stats()["active"] == 2


@pytest.mark.asyncio
async def test_http_deadline_releases_a_stream_stalled_in_asgi_send(monkeypatch):
    executor = InferenceExecutor(max_queue=1)
    registry = CancellationRegistry()
    monkeypatch.setattr(worker, "executor", executor)
    monkeypatch.setattr(worker, "_cancellations", registry)
    monkeypatch.setattr(worker, "_produce_chunks", lambda req, output: None)
    req = worker.SynthesizeRequest(
        call_id="c",
        generation_id="g",
        phrase_id="p",
        text="Поняла.",
        deadline=time.monotonic() + 0.05,
    )
    stream = worker._prepare_stream(req)
    await asyncio.wrap_future(stream.future)
    assert registry.stats()["active"] == 1

    async def stuck(*args):
        await asyncio.Event().wait()

    try:
        with pytest.raises(TimeoutError):
            await worker._InferenceResponse(req, stream)(
                {"type": "http", "asgi": {"spec_version": "2.4"}}, stuck, stuck
            )
        assert registry.stats()["active"] == 0
        assert executor.queue_depth == 0
    finally:
        stream.close()
        executor.shutdown()


@pytest.mark.asyncio
async def test_stream_byte_budget_applies_before_chunk_count_limit():
    executor = InferenceExecutor(max_queue=1)
    blocked = threading.Event()
    data = {"pcm_b64": "a" * 40}

    def produce(out_q):
        out_q.put(data)
        blocked.set()
        out_q.put(data)

    stream = BoundedInferenceStream(executor, produce, max_chunks=8, max_bytes=64)
    try:
        async with asyncio.timeout(1):
            while not blocked.is_set():
                await asyncio.sleep(0.005)
        assert stream.output.qsize() == 1
        assert stream.output.queued_bytes <= 64
        iterator = stream.items()
        assert await anext(iterator) == data
        assert await anext(iterator) == data
        with pytest.raises(StopAsyncIteration):
            await anext(iterator)
        assert stream.output.queued_bytes == 0
    finally:
        stream.close()
        executor._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_oversized_output_fails_instead_of_allocating_unbounded_queue():
    executor = InferenceExecutor(max_queue=1)
    stream = BoundedInferenceStream(
        executor,
        lambda out_q: out_q.put({"pcm_b64": "a" * 100}),
        max_bytes=64,
    )
    try:
        with pytest.raises(ValueError, match="byte budget"):
            await anext(stream.items())
    finally:
        stream.close()
        executor._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_active_identity_survives_completed_producer_until_consumer_settles(monkeypatch):
    executor = InferenceExecutor(max_queue=1)
    registry = CancellationRegistry(max_tombstones=1)
    monkeypatch.setattr(worker, "executor", executor)
    monkeypatch.setattr(worker, "_cancellations", registry)
    monkeypatch.setattr(
        worker, "_produce_chunks", lambda req, out_q: out_q.put({"pcm_b64": "AAA="})
    )
    req = worker.SynthesizeRequest(
        call_id="c",
        request_id="r",
        generation_id="g",
        phrase_id="p",
        text="Поняла.",
    )
    stream = worker._prepare_stream(req)
    try:
        await asyncio.wrap_future(stream.future)
        assert executor.queue_depth == 0
        assert registry.stats()["active"] == 1
        with pytest.raises(DuplicateRequestError):
            worker._prepare_stream(req)
        registry.cancel(generation_id="g")
        registry.cancel(request_id="evict-tombstone")
        frames = [json.loads(line) async for line in worker._ndjson_stream(req, stream)]
        assert frames == [{"done": True, "cancelled": True}]
        assert registry.stats()["active"] == 0
    finally:
        stream.close()
        executor._executor.shutdown(wait=True)


def production(monkeypatch):
    monkeypatch.setenv("IMVERA_RUNTIME_MODE", "production")
    monkeypatch.setenv("IMVERA_GIT_SHA", "a" * 40)
    monkeypatch.setenv("IMVERA_VOICE_PROFILE_PATH", "config/voice-linux-cpu.yaml")
    monkeypatch.setenv("IMVERA_QWEN_TTS_URL", "http://127.0.0.1:9")
    monkeypatch.delenv("IMVERA_TTS_ENGINE", raising=False)
    return yaml.safe_load(Path("config/voice-linux-cpu.yaml").read_text())


def test_all_workers_use_same_explicit_profile(monkeypatch, tmp_path):
    from services.llm import worker as llm
    from services.stt import worker as stt

    profile = tmp_path / "profile.yaml"
    profile.write_text("profile_id: portable-test\nports: {stt: 9911, tts: 9912, llm: 9913}\n")
    monkeypatch.setenv("IMVERA_VOICE_PROFILE_PATH", str(profile))
    for module in (worker, stt, llm):
        assert module._load_config()["profile_id"] == "portable-test"


@pytest.mark.parametrize("service", ["tts", "stt"])
def test_linux_production_profile_passes_known_backend_validation(monkeypatch, service):
    cfg = production(monkeypatch)
    validate_worker_config(cfg, service)
    assert load_worker_config(Path("missing.yaml"), service)["profile_id"] == cfg["profile_id"]


@pytest.mark.parametrize(
    "env", ["IMVERA_GIT_SHA", "IMVERA_VOICE_PROFILE_PATH", "IMVERA_QWEN_TTS_URL"]
)
def test_production_cannot_start_with_missing_identity(monkeypatch, env):
    cfg = production(monkeypatch)
    monkeypatch.delenv(env)
    with pytest.raises(RuntimeError, match="production requires"):
        validate_worker_config(cfg, "tts")


@pytest.mark.parametrize("engine", ["silero_lab", "unknown", "mlx_customvoice"])
def test_linux_production_rejects_lab_or_apple_only_backend(monkeypatch, engine):
    cfg = production(monkeypatch)
    monkeypatch.setattr("services.inference.config.sys.platform", "linux")
    monkeypatch.setenv("IMVERA_TTS_ENGINE", engine)
    with pytest.raises(RuntimeError):
        validate_worker_config(cfg, "tts")


@pytest.mark.parametrize("failure", ["server", "voice"])
def test_production_warmup_failure_never_selects_lab_voice(monkeypatch, failure):
    from services.tts import qwen_gguf

    production(monkeypatch)
    monkeypatch.setattr(worker.state, "ready", False)
    monkeypatch.setattr(worker.state, "warmup_error", None)
    monkeypatch.setattr(qwen_gguf, "ping", lambda: failure != "server")
    monkeypatch.setattr(qwen_gguf, "ensure_voice_registered", lambda _: False)
    monkeypatch.setattr(worker, "_init_silero_lab", lambda _: pytest.fail("lab fallback in prod"))
    worker._ping_and_warmup_qwen({"engine": "qwen_gguf"})
    assert worker.state.ready is False
    assert worker.state.warmup_error


def test_production_request_failure_never_synthesizes_another_voice(monkeypatch):
    cfg = production(monkeypatch)
    monkeypatch.setattr(worker, "_load_config", lambda: cfg)
    monkeypatch.setattr(worker, "_cancellations", CancellationRegistry())

    def failure(*args):
        raise RuntimeError("selected model unavailable")

    monkeypatch.setattr(worker, "_produce_qwen_chunks", failure)
    monkeypatch.setattr(worker, "_produce_silero_chunks", lambda *args: pytest.fail("lab fallback"))
    req = worker.SynthesizeRequest(call_id="c", generation_id="g", phrase_id="p", text="Поняла.")
    output = queue.Queue()
    worker._produce_chunks(req, output)
    assert output.get_nowait()["error"]
    assert output.get_nowait() is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("deadline", float("nan")),
        ("deadline", float("inf")),
        ("timeout_ms", 120001),
        ("generation_id", ""),
        ("request_id", "x" * 161),
        ("phrase_id", ""),
    ],
)
def test_request_limits_reject_ambiguous_identity_or_unbounded_time(field, value):
    payload = dict(call_id="c", generation_id="g", phrase_id="p", text="Поняла.")
    payload[field] = value
    with pytest.raises(ValidationError):
        worker.SynthesizeRequest(**payload)


def test_offline_production_model_artifacts_fail_before_download(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "services.stt.gigaam_engine._download_file", lambda *args: pytest.fail("download")
    )
    with pytest.raises(FileNotFoundError, match="downloads disabled"):
        ensure_gigaam_artifacts("v3_e2e_rnnt", tmp_path, allow_download=False)


def test_executor_shutdown_cancels_queued_work_without_lying_about_running_job():
    executor = InferenceExecutor(max_queue=2)
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def running():
        entered.set()
        release.wait(2)

    job = executor.submit(running)
    assert entered.wait(1)
    queued = executor.submit(lambda: calls.append("must not run"))
    try:
        executor.shutdown()
        assert queued.cancelled()
        assert executor.queue_depth == 1
        with pytest.raises(QueueFullError, match="draining"):
            executor.submit(lambda: None)
        release.set()
        job.result(timeout=1)
        assert calls == [] and executor.queue_depth == 0
    finally:
        release.set()
        executor._executor.shutdown(wait=True)


def test_hung_job_watchdog_does_not_report_the_running_model_as_completed():
    executor = InferenceExecutor(max_queue=1)
    state = WorkerState(ready=True)
    release = threading.Event()
    fatal = threading.Event()
    job = executor.submit(lambda: release.wait(2))
    guard = InferenceWatchdog(executor, state, max_job_s=0.03, poll_s=0.005, fatal=fatal.set)
    try:
        assert fatal.wait(1)
        assert state.ready is False
        assert "hard timeout" in state.warmup_error
        assert executor.queue_depth == 1 and not job.done()
        release.set()
        job.result(timeout=1)
    finally:
        guard.stop()
        release.set()
        executor._executor.shutdown(wait=True)


def test_default_watchdog_really_terminates_a_stuck_dedicated_process():
    program = """
import threading
from services.inference.common import InferenceExecutor, WorkerState
from services.inference.watchdog import InferenceWatchdog
executor = InferenceExecutor()
executor.submit(lambda: threading.Event().wait())
guard = InferenceWatchdog(executor, WorkerState(ready=True), max_job_s=.05, poll_s=.01)
threading.Event().wait()
"""
    result = subprocess.run([sys.executable, "-c", program], capture_output=True, timeout=5)
    assert result.returncode == 70
    assert b"hard timeout" in result.stderr


def test_startup_guard_really_terminates_hung_model_loading():
    program = """
import os, threading
from services.inference.common import WorkerState
from services.inference.watchdog import production_startup_guard
os.environ['IMVERA_RUNTIME_MODE'] = 'production'
with production_startup_guard(
    WorkerState(), {'limits': {'worker_startup_hard_timeout_s': .05}}
):
    threading.Event().wait()
"""
    result = subprocess.run([sys.executable, "-c", program], capture_output=True, timeout=5)
    assert result.returncode == 70
    assert b"startup exceeded" in result.stderr


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), 0, True, 601])
def test_production_rejects_unbounded_startup_timeout(monkeypatch, timeout):
    cfg = production(monkeypatch)
    cfg["limits"]["worker_startup_hard_timeout_s"] = timeout
    with pytest.raises(RuntimeError, match="startup timeout"):
        validate_worker_config(cfg, "tts")


def test_failed_production_boot_exits_for_supervisor_retry(monkeypatch):
    cfg = production(monkeypatch)
    monkeypatch.setattr(worker, "_load_config", lambda: cfg)
    monkeypatch.setattr(worker, "executor", InferenceExecutor())
    monkeypatch.setattr(worker.state, "ready", False)
    monkeypatch.setattr(worker, "_ping_and_warmup_qwen", lambda _: None)
    monkeypatch.setattr(worker.uvicorn, "run", lambda *args, **kwargs: pytest.fail("fake serving"))
    with pytest.raises(SystemExit) as exit_reason:
        worker.main()
    assert exit_reason.value.code == 70
