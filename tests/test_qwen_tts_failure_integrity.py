"""Qwen delivery/warmup failures preserve the actual provider and completion truth."""

from __future__ import annotations

import base64
import json
import os
import queue
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from services.providers.replica_pool import MidStreamUnavailable
from services.tts import qwen_gguf, worker
from services.tts.http_provider import HttpTTSProvider
from services.tts.warmup import warmup_synthesis

QWEN_PCM = b"\x01\x00" * 160
SILERO_PCM = b"\x02\x00" * 160
QWEN_REVISION = "qwen_gguf:qwen-talker-0.6b-customvoice-Q8_0"
SILERO_REVISION = "silero_lab:silero:v5_ru:kseniya"


@pytest.fixture
def qwen_worker(monkeypatch):
    cfg = {"engine": "qwen_gguf"}
    monkeypatch.setenv("IMVERA_TTS_ENGINE", "qwen_gguf")
    monkeypatch.setattr(worker, "_load_config", lambda: {"models": {"tts": cfg}})
    monkeypatch.setattr(worker.state, "ready", True)
    monkeypatch.setattr(worker.state, "model_revision", QWEN_REVISION)
    monkeypatch.setattr(worker.state, "warmup_error", None)
    monkeypatch.setattr(worker, "_cancelled", set())
    return cfg


def _partial_error(*_, **__):
    yield QWEN_PCM
    raise RuntimeError("Qwen read failed after PCM")


def _no_audio_error(*_, **__):
    raise RuntimeError("Qwen failed before PCM")
    yield  # Make this a provider stream, with failure on its first advance.


def _silero_callback(calls):
    def produce(req, out_q, cfg):
        calls.append(req.text)
        out_q.put({
            "sequence": 0, "sample_rate": 24000,
            "pcm_b64": base64.b64encode(SILERO_PCM).decode(), "is_last": False,
        })
        out_q.put(None)
    return produce


def test_partial_qwen_http_error_never_appends_silero(monkeypatch, qwen_worker) -> None:
    monkeypatch.setattr(qwen_gguf, "synthesize_stream", _partial_error)
    fallback_calls = []
    monkeypatch.setattr(worker, "_produce_silero_chunks", _silero_callback(fallback_calls))
    response = TestClient(worker.app).post("/v1/synthesize", json={
        "call_id": "failure-test", "generation_id": "partial", "phrase_id": "p",
        "text": "Здравствуйте.",
    })
    frames = [json.loads(line) for line in response.text.splitlines()]
    audio = [frame for frame in frames if "pcm_b64" in frame]
    assert response.status_code == 200  # Headers already preceded the emitted PCM.
    assert fallback_calls == []
    assert len(audio) == 1
    assert base64.b64decode(audio[0]["pcm_b64"]) == QWEN_PCM
    assert [frame["sequence"] for frame in audio] == [0]
    assert frames[-1]["done"] is True
    assert frames[-1].get("error")
    assert not any(frame.get("done") and not frame.get("error") for frame in frames)


@pytest.mark.asyncio
async def test_http_adapter_surfaces_partial_qwen_failure(monkeypatch, qwen_worker) -> None:
    monkeypatch.setattr(qwen_gguf, "synthesize_stream", _partial_error)
    fallback_calls = []
    monkeypatch.setattr(worker, "_produce_silero_chunks", _silero_callback(fallback_calls))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=worker.app), base_url="http://tts-test"
    ) as client:
        provider = HttpTTSProvider("http://tts-test", client=client)
        chunks = []
        with pytest.raises(MidStreamUnavailable):
            async for chunk in provider.synthesize(
                "Здравствуйте.", call_id="failure-test", generation_id="partial-adapter",
                phrase_id="p", deadline=time.monotonic() + 5,
            ):
                chunks.append(chunk)
    assert [chunk.pcm_s16le for chunk in chunks] == [QWEN_PCM]
    assert fallback_calls == []


def test_before_pcm_fallback_remains_clean_and_logs_actual_engine(
    monkeypatch, qwen_worker, capsys
) -> None:
    monkeypatch.setattr(qwen_gguf, "synthesize_stream", _no_audio_error)
    fallback_calls = []
    monkeypatch.setattr(worker, "_produce_silero_chunks", _silero_callback(fallback_calls))
    response = TestClient(worker.app).post("/v1/synthesize", json={
        "call_id": "failure-test", "generation_id": "cold-request", "phrase_id": "p",
        "text": "Здравствуйте.",
    })
    frames = [json.loads(line) for line in response.text.splitlines()]
    assert fallback_calls == ["Здравствуйте."]
    assert base64.b64decode(frames[0]["pcm_b64"]) == SILERO_PCM
    assert frames[-1] == {"done": True}
    log = capsys.readouterr().out
    assert "requested_engine=qwen_gguf" in log
    assert "actual_engine=silero_lab" in log
    assert "generation_id=cold-request" in log


def test_qwen_warmup_never_proves_readiness_with_per_request_fallback(
    monkeypatch, qwen_worker
) -> None:
    monkeypatch.setattr(qwen_gguf, "ping", lambda: True)
    monkeypatch.setattr(qwen_gguf, "synthesize_stream", _no_audio_error)
    fallback_calls = []
    monkeypatch.setattr(worker, "_produce_silero_chunks", _silero_callback(fallback_calls))
    cold_fallbacks = []

    def initialize(cfg):
        cold_fallbacks.append(cfg)
        os.environ["IMVERA_TTS_ENGINE"] = "silero_lab"
        worker.state.ready = True
        worker.state.model_revision = SILERO_REVISION
        return True

    monkeypatch.setattr(worker, "_init_silero_lab", initialize)
    worker._ping_and_warmup_qwen(qwen_worker)
    health = TestClient(worker.app).get("/health/ready")
    assert fallback_calls == []
    assert cold_fallbacks == [qwen_worker]
    assert health.status_code == 200
    assert health.json()["model_revision"] == SILERO_REVISION
    assert worker.tts_engine(qwen_worker) == "silero_lab"


def test_successful_qwen_warmup_proves_qwen(monkeypatch, qwen_worker) -> None:
    monkeypatch.setattr(qwen_gguf, "ping", lambda: True)
    monkeypatch.setattr(qwen_gguf, "synthesize_stream", lambda *_, **__: iter([QWEN_PCM]))
    monkeypatch.setattr(worker.state, "ready", False)
    monkeypatch.setattr(worker.state, "model_revision", "")
    monkeypatch.setattr(worker, "_init_silero_lab", lambda _: pytest.fail("unexpected fallback"))
    worker._ping_and_warmup_qwen(qwen_worker)
    health = TestClient(worker.app).get("/health/ready")
    assert health.status_code == 200
    assert health.json()["model_revision"] == QWEN_REVISION
    assert worker.tts_engine(qwen_worker) == "qwen_gguf"


@pytest.mark.parametrize("failure", ["ping", "warmup"])
def test_real_cold_fallback_init_reports_actual_silero(
    monkeypatch, qwen_worker, failure
) -> None:
    monkeypatch.setenv("IMVERA_SILERO_LAB_ACK", "1")
    monkeypatch.setattr(qwen_gguf, "ping", lambda: failure != "ping")
    monkeypatch.setattr(qwen_gguf, "synthesize_stream", _no_audio_error)
    monkeypatch.setattr("services.tts.silero_lab.load_silero", lambda _: (object(), None))
    per_request_calls = []
    monkeypatch.setattr(worker, "_produce_silero_chunks", _silero_callback(per_request_calls))
    worker._ping_and_warmup_qwen(qwen_worker)
    health = TestClient(worker.app).get("/health/ready")
    assert per_request_calls == []
    assert health.status_code == 200
    assert health.json()["model_revision"] == SILERO_REVISION
    assert worker.tts_engine(qwen_worker) == "silero_lab"


def test_warmup_propagates_error_after_pcm_and_sentinel() -> None:
    def produce(req, out_q):
        try:
            out_q.put({"pcm_b64": "AQABAA==", "sequence": 0, "sample_rate": 24000})
            raise RuntimeError("warmup producer failed after PCM")
        finally:
            out_q.put(None)

    with pytest.raises(RuntimeError, match="warmup producer failed after PCM"):
        warmup_synthesis(produce, timeout_s=0.5)


def test_warmup_timeout_does_not_accept_first_pcm_or_strand_queue_producer() -> None:
    stop = threading.Event()
    finished = threading.Event()
    queues = []

    def produce(req, out_q):
        queues.append(out_q)
        try:
            while not stop.is_set():
                out_q.put({"pcm_b64": "AQABAA==", "sequence": 0, "sample_rate": 24000})
        finally:
            finished.set()

    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            warmup_synthesis(produce, timeout_s=0.05)
        assert time.monotonic() - started < 1.0
        assert finished.wait(0.5)
    finally:
        stop.set()
        # Release the old implementation's blocked producer during baseline runs.
        deadline = time.monotonic() + 1.0
        while not finished.is_set() and time.monotonic() < deadline:
            try:
                queues[0].get_nowait()
            except (queue.Empty, IndexError):
                finished.wait(0.01)
