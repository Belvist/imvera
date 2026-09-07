"""Deterministic service/latency regressions, NOT a model-speed benchmark.

Run from the repo root, or set IMVERA_AUDIT_REPO. Requires project dev/api extras.
No model downloads, external requests, SIP calls, or production mutations.
"""

import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(os.environ.get("IMVERA_AUDIT_REPO", ".")).resolve()))

import httpx  # noqa: E402

from packages.contracts.semantic import TurnContext  # noqa: E402
from services.inference.common import InferenceExecutor  # noqa: E402
from services.llm import worker  # noqa: E402
from services.llm.http_provider import HttpLLMProvider  # noqa: E402

VALID_PAYLOAD = {
    "dialogue_act": "backchannel",
    "control": "none",
    "consent_answer": "not_applicable",
    "answers_pending_question": False,
    "needs_clarification": False,
}


def test_interpreter_request_carries_cancel_id_and_remaining_budget(monkeypatch):
    bodies = []

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, *, json):
            bodies.append(json)
            return httpx.Response(
                200,
                json={"payload": VALID_PAYLOAD},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    context = TurnContext(
        call_id="audit",
        turn_id=1,
        utterance_id="u1",
        state_version=0,
        raw_text="Алло",
        asr_quality="GOOD",
        pending_question_id=None,
        pending_question=None,
        pending_question_delivery="unknown",
    )
    asyncio.run(
        HttpLLMProvider("http://unused.test").interpret_turn(
            context,
            deadline=time.monotonic() + 3,
        )
    )
    assert {"request_id", "timeout_ms"} <= bodies[0].keys(), bodies[0].keys()


def test_render_worker_emits_before_consuming_entire_model_output(monkeypatch):
    generated = []

    def generate(*args, **kwargs):
        for text in ("Поняла.", " Как вы спали?"):
            generated.append(text)
            yield SimpleNamespace(text=text)

    class InlineExecutor:
        async def run(self, fn):
            return fn()

    monkeypatch.setitem(sys.modules, "mlx_lm", SimpleNamespace(stream_generate=generate))
    monkeypatch.setattr(
        worker,
        "_tokenizer",
        SimpleNamespace(apply_chat_template=lambda *args, **kwargs: "test prompt"),
    )
    monkeypatch.setattr(worker, "executor", InlineExecutor())
    monkeypatch.setattr(worker.state, "ready", True)

    async def scenario():
        response = await worker.render(worker.RenderRequest(action={"intent": "check_sleep"}))
        stream = response.body_iterator
        try:
            await anext(stream)
            assert len(generated) == 1, generated
        finally:
            await stream.aclose()

    asyncio.run(scenario())


def test_cancelled_queued_interpretation_never_starts_generation(monkeypatch):
    gate = threading.Event()
    executor = InferenceExecutor(max_queue=4)
    executor.submit(lambda: gate.wait(5))
    generated = []

    def generate(*args, **kwargs):
        generated.append("executed")
        return json.dumps(VALID_PAYLOAD)

    monkeypatch.setattr(worker, "executor", executor)
    monkeypatch.setattr(worker, "_generate_sync", generate)
    monkeypatch.setattr(worker, "_cancelled", set())
    monkeypatch.setattr(worker.state, "ready", True)

    async def scenario():
        req = worker.InterpretRequest(
            request_id="audit-cancel-queued",
            context={"raw_text": "Алло"},
        )
        task = asyncio.create_task(worker.interpret(req))
        try:
            deadline = time.monotonic() + 2
            while executor.queue_depth < 2 and not task.done():
                assert time.monotonic() < deadline, "Test setup did not enqueue request"
                await asyncio.sleep(0.005)
            assert not task.done()
            worker.cancel({"request_id": req.request_id})
            gate.set()
            await asyncio.gather(task, return_exceptions=True)
            assert not generated, "Request cancelled in queue still performed inference"
        finally:
            gate.set()
            await asyncio.gather(task, return_exceptions=True)

    try:
        asyncio.run(scenario())
    finally:
        gate.set()
        executor._executor.shutdown(wait=True)


def test_health_reports_actual_outstanding_inference(monkeypatch):
    gate = threading.Event()
    executor = InferenceExecutor(max_queue=4)
    executor.submit(lambda: gate.wait(5))
    monkeypatch.setattr(worker, "executor", executor)
    monkeypatch.setattr(worker.state, "ready", True)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=worker.app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")
            data = response.json()
        assert data["queue_depth"] == executor.queue_depth == 1, data

    try:
        asyncio.run(scenario())
    finally:
        gate.set()
        executor._executor.shutdown(wait=True)
