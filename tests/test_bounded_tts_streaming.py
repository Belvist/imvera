"""Streaming/cancellation boundaries with real worker, HTTP adapter and actor."""

from __future__ import annotations

import asyncio
import base64
import json
import socket
import threading
import time
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
import uvicorn
from fastapi import HTTPException

from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.voice_runtime.call_actor import CallActor, CallActorConfig, MediaCallbacks
from packages.voice_runtime.playback import PlaybackQueue
from services.inference.common import InferenceExecutor
from services.inference.streaming import BoundedInferenceStream
from services.providers.replica_pool import MidStreamUnavailable
from services.tts import worker
from services.tts.http_provider import HttpTTSProvider
from services.tts.sentence_stream import sentence_segments


async def settled(executor: InferenceExecutor) -> None:
    async with asyncio.timeout(1):
        while executor.queue_depth:
            await asyncio.sleep(0.005)


@pytest.fixture
def tts_worker(monkeypatch):
    executor = InferenceExecutor(max_queue=1)
    monkeypatch.setattr(worker, "executor", executor)
    monkeypatch.setattr(worker, "_cancelled", set())
    monkeypatch.setattr(worker.state, "cancelled_requests", set())
    monkeypatch.setattr(worker.state, "ready", True)
    monkeypatch.setattr(
        worker, "_load_config", lambda: {"models": {"tts": {"engine": "silero_lab"}}}
    )
    monkeypatch.setenv("IMVERA_TTS_ENGINE", "silero_lab")
    monkeypatch.delenv("IMVERA_TTS_SENTENCE_STREAM", raising=False)
    yield executor
    executor._executor.shutdown(wait=True)


def request(**changes):
    return worker.SynthesizeRequest(
        call_id="stream-test",
        generation_id="g-test",
        phrase_id="p-test",
        text="Поняла. Как вы сегодня себя чувствуете?",
        **changes,
    )


@pytest.mark.asyncio
async def test_disconnect_unblocks_full_queue_and_releases_real_inference_slot(
    monkeypatch, tts_worker
):
    full = threading.Event()
    queues = []

    def produce(req, out_q):
        queues.append(out_q)
        for _ in range(1000):
            if out_q.full():
                full.set()
            out_q.put({"pcm_b64": "AQABAA==", "sample_rate": 16000})

    monkeypatch.setattr(worker, "_produce_chunks", produce)
    response = await worker.synthesize(request())
    body = response.body_iterator
    await anext(body)
    async with asyncio.timeout(1):
        while not full.is_set():
            await asyncio.sleep(0.005)
    assert queues[0].qsize() <= 8
    await asyncio.wait_for(body.aclose(), timeout=0.2)
    await settled(tts_worker)
    assert await tts_worker.run(lambda: "next caller") == "next caller"


@pytest.mark.asyncio
async def test_cancel_before_headers_releases_admitted_producer(monkeypatch, tts_worker):
    def produce(req, out_q):
        for _ in range(1000):
            out_q.put({"pcm_b64": "AQABAA=="})

    monkeypatch.setattr(worker, "_produce_chunks", produce)
    response = await worker.synthesize(request())

    async def send(message):
        raise asyncio.CancelledError()

    async def receive():
        await asyncio.Future()

    with pytest.raises(asyncio.CancelledError):
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    await settled(tts_worker)


@pytest.mark.asyncio
async def test_overload_rejected_before_stream_headers(monkeypatch, tts_worker):
    release = threading.Event()
    job = tts_worker.submit(lambda: release.wait(1))
    try:
        with pytest.raises(HTTPException) as error:
            await worker.synthesize(request())
        assert error.value.status_code == 429
    finally:
        release.set()
        await asyncio.wrap_future(job)


@pytest.mark.asyncio
async def test_relative_deadline_prevents_work_from_waiting_behind_an_old_job(
    monkeypatch, tts_worker
):
    # One running job + one queued request. Expired queued work must not synthesize.
    executor = InferenceExecutor(max_queue=2)
    monkeypatch.setattr(worker, "executor", executor)
    release = threading.Event()
    job = executor.submit(lambda: release.wait(1))
    calls = []
    monkeypatch.setattr(worker, "_produce_chunks", lambda req, out_q: calls.append(req.text))
    try:
        response = await worker.synthesize(request(timeout_ms=10, deadline=time.monotonic() + 100))
        await asyncio.sleep(0.025)
        frames = [json.loads(line) async for line in response.body_iterator]
        assert frames == [{"done": True, "error": "deadline exceeded"}]
        release.set()
        await asyncio.wrap_future(job)
        await settled(executor)
        assert calls == []
    finally:
        release.set()
        executor._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_running_kernel_retains_capacity_after_consumer_cancel():
    executor = InferenceExecutor(max_queue=1)
    started = threading.Event()
    release = threading.Event()

    def produce(out_q):
        started.set()
        release.wait(1)
        out_q.put("late PCM")

    stream = BoundedInferenceStream(executor, produce)
    try:
        async with asyncio.timeout(1):
            while not started.is_set():
                await asyncio.sleep(0.005)
        stream.close()
        assert executor.queue_depth == 1
        release.set()
        await settled(executor)
        assert stream.output.empty()
    finally:
        release.set()
        executor._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_cancel_request_id_stops_blocked_producer(monkeypatch, tts_worker):
    def produce(req, out_q):
        for _ in range(1000):
            out_q.put({"pcm_b64": "AQABAA=="})

    monkeypatch.setattr(worker, "_produce_chunks", produce)
    req = request()
    response = await worker.synthesize(req)
    await anext(response.body_iterator)
    worker.cancel({"request_id": req.request_id})
    frames = [json.loads(line) async for line in response.body_iterator]
    assert frames == [{"done": True, "cancelled": True}]
    await settled(tts_worker)


@pytest.mark.asyncio
async def test_failure_after_sentinel_is_not_success(monkeypatch, tts_worker):
    def produce(req, out_q):
        out_q.put({"pcm_b64": "AQABAA==", "sample_rate": 16000})
        out_q.put(None)
        raise RuntimeError("producer failed after sentinel")

    monkeypatch.setattr(worker, "_produce_chunks", produce)
    response = await worker.synthesize(request())
    frames = [json.loads(line) async for line in response.body_iterator]
    assert "pcm_b64" in frames[0]
    assert frames[-1] == {"done": True, "error": "producer failed after sentinel"}
    await settled(tts_worker)


@pytest.mark.asyncio
async def test_http_adapter_sends_relative_timeout_not_remote_monotonic_clock():
    payloads = []

    def endpoint(req):
        payloads.append(json.loads(req.content))
        return httpx.Response(200, text='{"done": true}\n')

    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as client:
        provider = HttpTTSProvider("http://tts", client=client)
        chunks = [
            chunk
            async for chunk in provider.synthesize(
                "Поняла.",
                call_id="c",
                generation_id="g",
                phrase_id="p",
                deadline=time.monotonic() + 2,
            )
        ]
    assert chunks == []
    assert 0 < payloads[0]["timeout_ms"] <= 2000
    assert "deadline" not in payloads[0]


@pytest.mark.parametrize(
    "text",
    [
        "Доза 2.5 мг. Как вы себя чувствуете?",
        "А. И. Иванова живёт на ул. Ленина. Она отдыхает.",
        "Принимали 1 табл. утром. Как вы себя чувствуете?",
        "Поняла. Как вы спали?",
        "Поняла… Расскажите, пожалуйста.",
    ],
)
def test_sentence_boundaries_preserve_text_and_do_not_split_dose_or_initials(text):
    segments = sentence_segments(text)
    assert "".join(segments) == text
    assert not any(
        segment.rstrip().endswith(("2.", "А.", "И.", "ул.", "табл.")) for segment in segments
    )


@pytest.mark.asyncio
async def test_opt_in_sentence_mode_delivers_first_pcm_before_second_synthesis(
    monkeypatch, tts_worker
):
    monkeypatch.setenv("IMVERA_TTS_SENTENCE_STREAM", "1")
    release = threading.Event()
    second_started = threading.Event()
    calls = []

    def synthesize(text, cfg):
        calls.append(text)
        if len(calls) == 2:
            second_started.set()
            assert release.wait(1), (
                "consumer must receive first PCM before completing second sentence"
            )
        return np.ones(320, dtype=np.float32), 16000

    monkeypatch.setattr(worker, "synthesize_silero", synthesize)
    response = await worker.synthesize(request())
    try:
        first = json.loads(await asyncio.wait_for(anext(response.body_iterator), timeout=0.2))
        assert base64.b64decode(first["pcm_b64"])
        assert not release.is_set()
        release.set()
        rest = [json.loads(line) async for line in response.body_iterator]
        assert rest[-1] == {"done": True}
        assert "".join(calls) == request().text
        assert second_started.is_set()
    finally:
        release.set()
        await response.body_iterator.aclose()
        await settled(tts_worker)


@pytest.mark.asyncio
async def test_default_sentence_mode_is_off(monkeypatch, tts_worker):
    calls = []

    def synthesize(text, cfg):
        calls.append(text)
        return np.ones(320, dtype=np.float32), 16000

    monkeypatch.setattr(worker, "synthesize_silero", synthesize)
    response = await worker.synthesize(request())
    frames = [json.loads(line) async for line in response.body_iterator]
    assert calls == [request().text]
    assert frames[-1] == {"done": True}
    await settled(tts_worker)


@pytest.mark.asyncio
async def test_truncated_pcm_stream_is_failure_without_replaying_another_replica():
    urls = []

    def endpoint(req):
        urls.append(str(req.url))
        return httpx.Response(200, text='{"pcm_b64": "AQABAA==", "sample_rate": 16000}\n')

    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as client:
        provider = HttpTTSProvider("http://first,http://second", client=client)
        received = []
        with pytest.raises(MidStreamUnavailable, match="mid-stream"):
            async for chunk in provider.synthesize(
                "Поняла.",
                call_id="c",
                generation_id="g",
                phrase_id="p",
                deadline=time.monotonic() + 2,
            ):
                received.append(chunk)
    assert len(received) == 1
    assert len(urls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("interrupt", [False, True])
async def test_real_http_and_call_actor_send_pcm_while_later_sentence_is_still_generating(
    monkeypatch,
    tts_worker,
    interrupt,
):
    # ASGITransport buffers a complete response, so this proof uses actual TCP.
    # The synthesis fixture is controlled, not a model/voice performance claim.
    monkeypatch.setenv("IMVERA_TTS_SENTENCE_STREAM", "1")
    release = threading.Event()
    calls = []

    def synthesize(text, cfg):
        calls.append(text)
        if len(calls) == 2:
            assert release.wait(2), "first PCM must reach transport before remaining synthesis"
        return np.ones(320, dtype=np.float32), 16000

    monkeypatch.setattr(worker, "synthesize_silero", synthesize)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(worker.app, log_level="error", lifespan="off"))
    server_task = asyncio.create_task(server.serve(sockets=[listener]))
    actor = None
    speak_task = None
    async with httpx.AsyncClient() as client:
        try:
            async with asyncio.timeout(2):
                while not server.started:
                    await asyncio.sleep(0.005)
            sent = []
            first_send = asyncio.Event()

            async def send_pcm(pcm):
                sent.append(pcm)
                first_send.set()

            async def noop(*args, **kwargs):
                return None

            session = CallSession(
                call_id="real-stream",
                family_id="test",
                store=InMemoryCallRecordStore(),
            )
            actor = CallActor(
                call_id="real-stream",
                family_id="test",
                session=session,
                stt=SimpleNamespace(),
                llm=SimpleNamespace(cancel_request=noop),
                tts=HttpTTSProvider(f"http://127.0.0.1:{port}", client=client),
                media=MediaCallbacks(send_pcm, noop, noop, noop),
                config=CallActorConfig(telephony_stream=False, post_speech_pause_ms=0),
            )
            actor._playback = PlaybackQueue(call_id=actor.call_id, sample_rate=16000)
            actor._playback_task = asyncio.create_task(actor._playback_pump())
            actor._render_generation = "g-real-stream"
            text = request().text
            speak_task = asyncio.create_task(actor._speak_phrase(text, "g-real-stream"))
            await asyncio.wait_for(first_send.wait(), timeout=1)
            assert not speak_task.done()
            assert actor._playback._ledger.canonical_text == text
            assert actor._playback._ledger.generation_done is False
            assert release.is_set() is False
            if interrupt:
                await actor._interrupt_playback(flush=True)
                sent_at_cancel = list(sent)
            release.set()
            await asyncio.wait_for(speak_task, timeout=2)
            if interrupt:
                await settled(tts_worker)
                assert sent == sent_at_cancel
                assert actor._render_generation is None
                # The echo-reference list deliberately retains partially heard
                # text. Only the playback ledger establishes completion.
                assert actor._playback._ledger.interrupted is True
                assert actor._playback._ledger.generation_done is False
                assert actor._playback._ledger.generation_outcome != "success"
                assert actor._playback.is_cancelled("g-real-stream")
            else:
                assert "".join(calls) == text
                assert len(b"".join(sent)) == 640 * 2
                assert actor._delivered_phrases == [text]
                assert actor._playback._ledger.generation_outcome == "success"
        finally:
            release.set()
            if speak_task is not None and not speak_task.done():
                speak_task.cancel()
                await asyncio.gather(speak_task, return_exceptions=True)
            if actor is not None:
                actor._stopped = True
                await actor._shutdown_runtime_tasks()
            server.should_exit = True
            await asyncio.wait_for(server_task, timeout=2)
            listener.close()
            await settled(tts_worker)
