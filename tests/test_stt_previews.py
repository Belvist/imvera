"""Batch prefix observations and cancellation contracts, without model weights.

The WAV-reading backend is an inference boundary fixture; these tests do not
measure GigaAM accuracy, M5 throughput, live latency or listener warmth.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from packages.contracts.providers import ProviderInvalidOutput, ProviderUnavailable
from packages.contracts.runtime import RuntimeEventType
from packages.contracts.stt import STTPartial, STTResult
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.voice_runtime.call_actor import CallActor, CallActorConfig, MediaCallbacks
from packages.voice_runtime.utterance_builder import UtteranceBuilder
from packages.voice_runtime.vad import EnergyVad, VadConfig
from services.inference.common import InferenceExecutor
from services.stt import worker
from services.stt.http_provider import HttpSTTProvider

PCM_FRAME = b"\x10\x10" * 320


async def noop(*args, **kwargs):
    return None


class WavReader:
    def __init__(self):
        self.inputs = []
        self.paths = []

    def transcribe_wav(self, path):
        self.paths.append(Path(path))
        with wave.open(str(path), "rb") as wav:
            self.inputs.append(wav.readframes(wav.getnframes()))
        # Revisions may reverse meaning; caller must never treat preview as fact.
        return "болит" if len(self.inputs[-1]) == 32000 else "не болит"


@pytest.fixture
def stt_worker(monkeypatch):
    ex = InferenceExecutor(max_queue=4)
    backend = WavReader()
    monkeypatch.setattr(worker, "executor", ex)
    monkeypatch.setattr(worker.state, "ready", True)
    monkeypatch.setattr(worker.state, "model_revision", "fixture:gigaam")
    monkeypatch.setattr(worker.state, "cancelled_requests", set())
    monkeypatch.setattr(worker, "_asr", backend)
    monkeypatch.setattr(worker, "_load_config", lambda: {"models": {"asr": {"engine": "gigaam"}}})
    monkeypatch.setenv("IMVERA_STT_PREVIEW", "1")
    yield backend, ex
    ex._executor.shutdown(wait=True)


def request(*, rid="request", pcm=None, timeout_s=None):
    return worker.TranscribeRequest(
        request_id=rid, call_id="call", sample_rate=16000,
        pcm_b64=base64.b64encode(pcm or PCM_FRAME * 50).decode(), timeout_s=timeout_s,
    )


def test_real_http_provider_worker_prefixes_are_revisable_and_final_is_separate(stt_worker):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=worker.app),
                                     base_url="http://stt") as client:
            provider = HttpSTTProvider("http://stt", client=client, prefix_previews=True)
            caps = await provider.capabilities()
            assert caps.partial_mode == "prefix_batch" and not caps.native_streaming
            assert caps.final_required and caps.revisable
            assert caps.preview_checkpoints_ms == (1000, 2000, 4000, 8000)
            first = await provider.transcribe_partial(
                PCM_FRAME * 50, 16000, call_id="call", partial_id="p1")
            second = await provider.transcribe_partial(
                PCM_FRAME * 100, 16000, call_id="call", partial_id="p2")
            final = await provider.transcribe_final(
                PCM_FRAME * 150, 16000, call_id="call", turn_id=1,
                utterance_id="u-1", deadline=time.monotonic() + 5)
        assert first.text != second.text
        assert not first.is_final and not second.is_final and final.is_final
        assert first.model_revision == second.model_revision == final.model_revision
        assert stt_worker[0].inputs == [PCM_FRAME * 50, PCM_FRAME * 100, PCM_FRAME * 150]
        assert all(not path.exists() for path in stt_worker[0].paths)

    asyncio.run(scenario())


def test_preview_disabled_is_explicit_and_final_still_works(stt_worker, monkeypatch):
    monkeypatch.setenv("IMVERA_STT_PREVIEW", "0")

    async def scenario():
        assert worker.capabilities()["partial_mode"] == "unsupported"
        with pytest.raises(HTTPException) as error:
            await worker.preview(worker.PreviewRequest(**request().model_dump(exclude_none=True),
                                                       partial_id="p"))
        assert error.value.status_code == 503
        await worker.transcribe(request())
        assert len(stt_worker[0].inputs) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("pcm", [PCM_FRAME * 25, PCM_FRAME * 450, PCM_FRAME + b"\x00"],
                         ids=["below_checkpoint", "above_cap", "odd_sample"])
def test_preview_rejects_unbounded_or_misaligned_pcm_before_inference(stt_worker, pcm):
    async def scenario():
        with pytest.raises(HTTPException) as error:
            await worker.preview(worker.PreviewRequest(
                **request(pcm=pcm).model_dump(exclude_none=True), partial_id="p"))
        assert error.value.status_code in {400, 422}
        assert not stt_worker[0].inputs

    asyncio.run(scenario())


def test_busy_worker_skips_preview_without_queueing_but_accepts_final(stt_worker):
    async def scenario():
        backend, ex = stt_worker
        gate = threading.Event()
        ex.submit(lambda: gate.wait(3))
        try:
            with pytest.raises(HTTPException) as error:
                await worker.preview(worker.PreviewRequest(
                    **request().model_dump(exclude_none=True), partial_id="p"))
            assert error.value.status_code == 429 and ex.queue_depth == 1
            task = asyncio.create_task(worker.transcribe(request(rid="final")))
            await wait_until(lambda: ex.queue_depth == 2)
            assert not backend.inputs
            gate.set()
            await task
            assert len(backend.inputs) == 1
        finally:
            gate.set()

    asyncio.run(scenario())


async def wait_until(predicate):
    deadline = time.monotonic() + 2
    while not predicate():
        assert time.monotonic() < deadline, "test setup did not reach expected boundary"
        await asyncio.sleep(0.002)


@pytest.mark.parametrize("abort", ["cancel_endpoint", "http_cancel", "expire"])
def test_queued_aborted_final_does_not_open_wav_or_call_model(stt_worker, abort):
    async def scenario():
        backend, ex = stt_worker
        gate = threading.Event()
        ex.submit(lambda: gate.wait(3))
        task = asyncio.create_task(worker.transcribe(request(
            timeout_s=0.001 if abort == "expire" else None)))
        try:
            await wait_until(lambda: ex.queue_depth == 2)
            if abort == "cancel_endpoint":
                worker.cancel({"request_id": "request"})
            elif abort == "http_cancel":
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            else:
                await asyncio.sleep(0.005)
            gate.set()
            result = (await asyncio.gather(task, return_exceptions=True))[0]
            await wait_until(lambda: ex.queue_depth == 0)
            assert not backend.inputs and not backend.paths
            if abort != "http_cancel":
                assert isinstance(result, HTTPException)
                assert result.status_code == (503 if abort == "expire" else 499)
        finally:
            gate.set()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_inflight_http_cancel_keeps_wav_alive_until_model_returns_and_cleans_it(stt_worker,
                                                                             monkeypatch):
    entered, release = threading.Event(), threading.Event()
    paths = []

    def slow(path):
        paths.append(Path(path))
        entered.set()
        assert release.wait(3)
        with wave.open(str(path), "rb") as wav:
            assert wav.readframes(wav.getnframes()) == PCM_FRAME * 50
        return "не болит"

    monkeypatch.setattr(stt_worker[0], "transcribe_wav", slow)

    async def scenario():
        task = asyncio.create_task(worker.transcribe(request()))
        try:
            await wait_until(entered.is_set)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            assert paths[0].exists(), "request cancellation must not delete model input"
            release.set()
            await wait_until(lambda: stt_worker[1].queue_depth == 0)
            assert not paths[0].exists()
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_stt_health_reports_real_executor_load(stt_worker):
    async def scenario():
        gate = threading.Event()
        stt_worker[1].submit(lambda: gate.wait(3))
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=worker.app),
                                         base_url="http://stt") as client:
                health = (await client.get("/health/ready")).json()
            assert health["queue_depth"] == stt_worker[1].queue_depth == 1
        finally:
            gate.set()

    asyncio.run(scenario())


@pytest.mark.parametrize("bad", ["final", "identity", "mode"])
def test_provider_quarantines_misaddressed_or_final_preview(bad):
    async def scenario():
        def respond(req):
            body = json.loads(req.content)
            data = {"request_id": body["request_id"], "partial_id": body["partial_id"],
                    "is_final": False, "partial_mode": "prefix_batch", "text": "болит"}
            data[{"final": "is_final", "identity": "partial_id", "mode": "partial_mode"}[bad]] = (
                True if bad == "final" else "wrong")
            return httpx.Response(200, json=data)

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            provider = HttpSTTProvider("http://stt", client=client, prefix_previews=True)
            with pytest.raises(ProviderInvalidOutput):
                await provider.transcribe_partial(PCM_FRAME * 50, 16000,
                                                  call_id="call", partial_id="p")

    asyncio.run(scenario())


def test_preview_busy_is_not_retried_on_other_replicas():
    async def scenario():
        requests = []

        def busy(req):
            requests.append(str(req.url))
            return httpx.Response(429)

        async with httpx.AsyncClient(transport=httpx.MockTransport(busy)) as client:
            provider = HttpSTTProvider("http://one,http://two", client=client,
                                       prefix_previews=True)
            with pytest.raises(ProviderUnavailable):
                await provider.transcribe_partial(PCM_FRAME * 50, 16000,
                                                  call_id="call", partial_id="p")
        assert requests == ["http://one/v1/preview"]

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["preview", "final"])
@pytest.mark.parametrize("abort", ["task_cancel", "socket_timeout"])
def test_provider_cancels_exact_request_and_sends_relative_server_budget(kind, abort):
    async def scenario():
        entered = asyncio.Event()
        requests = []

        async def respond(req):
            body = json.loads(req.content)
            requests.append((req.url.path, body))
            if req.url.path == "/v1/cancel":
                return httpx.Response(200, json={"status": "accepted"})
            entered.set()
            if abort == "socket_timeout":
                raise httpx.ReadTimeout("boundary fixture", request=req)
            await asyncio.Event().wait()

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            provider = HttpSTTProvider("http://stt", client=client, prefix_previews=True)
            if kind == "preview":
                work = provider.transcribe_partial(PCM_FRAME * 50, 16000,
                                                   call_id="call", partial_id="p")
            else:
                work = provider.transcribe_final(PCM_FRAME * 50, 16000,
                                                 call_id="call", turn_id=1,
                                                 deadline=time.monotonic() + 1)
            task = asyncio.create_task(work)
            await entered.wait()
            if abort == "task_cancel":
                task.cancel()
            result = (await asyncio.gather(task, return_exceptions=True))[0]
        assert isinstance(result, asyncio.CancelledError if abort == "task_cancel"
                          else ProviderUnavailable)
        assert len(requests) == 2 and requests[1][0] == "/v1/cancel"
        assert requests[1][1]["request_id"] == requests[0][1]["request_id"]
        assert 0 < requests[0][1]["timeout_s"] <= (2 if kind == "preview" else 1)
        assert "deadline" not in requests[0][1], "host monotonic clocks are not interchangeable"

    asyncio.run(scenario())


def test_final_provider_rejects_nonfinal_result():
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json={"text": "не звоните", "is_final": False})
        )) as client:
            provider = HttpSTTProvider("http://stt", client=client)
            with pytest.raises(ProviderInvalidOutput, match="non-final"):
                await provider.transcribe_final(PCM_FRAME, 16000, call_id="call",
                                                 turn_id=1, deadline=time.monotonic() + 1)

    asyncio.run(scenario())


def audio_actor(stt, events):
    async def emit(event):
        events.append(event)

    session = CallSession(call_id="preview", family_id="family", store=InMemoryCallRecordStore())
    actor = CallActor(
        call_id="preview", family_id="family", session=session, stt=stt,
        tts=SimpleNamespace(cancel=noop), llm=SimpleNamespace(cancel_request=noop),
        media=MediaCallbacks(noop, noop, noop, emit),
        config=CallActorConfig(stt_prefix_previews=True, lab_half_duplex=False),
    )
    actor._vad = EnergyVad(16000, VadConfig(min_speech_ms=100, min_silence_ms=650))
    actor._utterance_builder = actor._collector = UtteranceBuilder(16000)
    return actor


@pytest.mark.dialogue_engine
def test_actor_previews_never_mutate_sdk_or_speak_and_final_alone_reaches_engine():
    async def scenario():
        events, previews, finals = [], [], []

        async def partial(pcm, sr, **kwargs):
            previews.append(pcm)
            return STTPartial(text="Да, согласен. Голова болит. Не звоните больше.",
                              partial_id=kwargs["partial_id"], partial_mode="prefix_batch")

        async def final(pcm, sr, **kwargs):
            finals.append(pcm)
            return STTResult(text="До свидания.")

        actor = audio_actor(SimpleNamespace(transcribe_partial=partial, transcribe_final=final),
                            events)
        initial = actor.session.start()
        actor.session.mark_spoken_action(initial.speak_effect.generation_id)
        engine = actor.session._engine
        before = copy.deepcopy(engine.state)
        revision = engine.revision
        actor._deliver_session_turn = noop
        for _ in range(115):
            await actor._process_uplink_vad_frame(PCM_FRAME, playback_active=False)
            await asyncio.sleep(0)
        assert previews and engine.state == before and engine.revision == revision
        assert any(event.event_type == RuntimeEventType.STT_PARTIAL for event in events)
        assert not any(event.event_type == RuntimeEventType.RENDERER_PHRASE_READY
                       for event in events)
        for _ in range(45):
            await actor._process_uplink_vad_frame(bytes(640), playback_active=False)
            await asyncio.sleep(0)
        await wait_until(lambda: actor._last_applied_utterance_seq == 1)
        assert len(finals) == 1 and len(finals[0]) > len(previews[-1])
        assert engine.revision > revision
        assert engine.state.call_closed and engine.state.closing_reason == "goodbye"
        assert not engine.state.issue_episodes, "preview headache must not become a clinical fact"
        await actor._cancel_engine_timer()

    asyncio.run(scenario())


@pytest.mark.parametrize("boundary", ["endpoint", "reset", "stop", "playback"])
def test_late_preview_is_dropped_even_when_provider_ignores_cancellation(boundary):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        events = []

        async def partial(pcm, sr, **kwargs):
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            return STTPartial(text="старый текст", partial_id=kwargs["partial_id"],
                              partial_mode="prefix_batch")

        actor = audio_actor(SimpleNamespace(transcribe_partial=partial), events)
        actor._handle_utterance = noop
        for _ in range(60):
            await actor._process_uplink_vad_frame(PCM_FRAME, playback_active=False)
            await asyncio.sleep(0)
        await asyncio.wait_for(entered.wait(), timeout=1)
        old_task = actor._stt_preview_task
        if boundary == "endpoint":
            for _ in range(45):
                await actor._process_uplink_vad_frame(bytes(640), playback_active=False)
                await asyncio.sleep(0)
        elif boundary == "reset":
            actor._reset_uplink_endpointing()
        elif boundary == "stop":
            await actor.stop()
        else:
            actor._on_bot_playback_started()
        release.set()
        await old_task
        assert not any(event.event_type == RuntimeEventType.STT_PARTIAL for event in events)

    asyncio.run(scenario())


def test_actor_preview_work_is_bounded_to_four_exact_prefixes_for_a_long_turn():
    async def scenario():
        prefixes = []

        async def partial(pcm, sr, **kwargs):
            prefixes.append(pcm)
            return STTPartial(text="промежуточный текст", partial_id=kwargs["partial_id"],
                              partial_mode="prefix_batch")

        actor = audio_actor(SimpleNamespace(transcribe_partial=partial), [])
        actor._handle_utterance = noop
        for _ in range(750):
            await actor._process_uplink_vad_frame(PCM_FRAME, playback_active=False)
            await asyncio.sleep(0)
        assert list(map(len, prefixes)) == [32000, 64000, 128000, 256000]
        assert sum(map(len, prefixes)) == 15 * 32000
        assert actor._utterance_seq == 0, "previews must not prematurely endpoint long speech"
        actor._reset_uplink_endpointing()

    asyncio.run(scenario())


def test_slow_preview_skips_checkpoints_and_final_does_not_wait_for_it():
    async def scenario():
        release, entered = asyncio.Event(), asyncio.Event()
        previews, finals = [], []

        async def partial(pcm, sr, **kwargs):
            previews.append(pcm)
            entered.set()
            await release.wait()

        async def final(pcm, seq):
            finals.append(pcm)

        events = []
        actor = audio_actor(SimpleNamespace(transcribe_partial=partial), events)
        actor._handle_utterance = final
        for _ in range(250):
            await actor._process_uplink_vad_frame(PCM_FRAME, playback_active=False)
            await asyncio.sleep(0)
        assert entered.is_set() and len(previews) == 1
        for _ in range(45):
            await actor._process_uplink_vad_frame(bytes(640), playback_active=False)
            await asyncio.sleep(0)
        assert len(finals) == 1 and not release.is_set()
        skipped = [event for event in events
                   if event.payload.get("stage") == "stt.preview.skipped"]
        assert len(skipped) == 2
        release.set()

    asyncio.run(scenario())


def test_preview_default_off_uses_only_the_existing_final_path():
    async def scenario():
        events, finals = [], []
        actor = audio_actor(SimpleNamespace(), events)
        actor.config = CallActorConfig(lab_half_duplex=False)

        async def final(pcm, seq):
            finals.append(pcm)

        actor._handle_utterance = final
        for frame in [PCM_FRAME] * 150 + [bytes(640)] * 45:
            await actor._process_uplink_vad_frame(frame, playback_active=False)
            await asyncio.sleep(0)
        assert len(finals) == 1 and actor._stt_preview_task is None
        assert not any(event.payload.get("stage", "").startswith("stt.preview")
                       for event in events)

    asyncio.run(scenario())
