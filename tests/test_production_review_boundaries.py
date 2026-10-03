"""Fault boundaries found by the production re-review; no neural quality claim."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest

from services.tts.http_provider import HttpTTSProvider


@pytest.mark.asyncio
async def test_replica_cancel_reaches_healthy_worker_inside_actor_cleanup_budget():
    blocked = threading.Event()
    reached = threading.Event()
    released = threading.Event()
    bodies = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return None

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.server is slow:
                blocked.set()
                released.wait(3)
            else:
                bodies.append(body)
                reached.set()
            try:
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()
            except OSError:
                return

    slow = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    healthy = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (slow, healthy)]
    for thread in threads:
        thread.start()
    try:
        async with httpx.AsyncClient() as client:
            provider = HttpTTSProvider(
                f"http://127.0.0.1:{slow.server_port},http://127.0.0.1:{healthy.server_port}",
                client=client,
            )
            before = set(asyncio.all_tasks())
            with pytest.raises(TimeoutError):
                # CallActor._watch_cleanup cancels provider work at 250ms.
                await asyncio.wait_for(provider.cancel("generation-under-test"), timeout=0.25)
            assert blocked.is_set()
            assert reached.is_set(), "a slow replica prevented cancellation of the playing worker"
            assert bodies == [{"generation_id": "generation-under-test"}]
            assert set(asyncio.all_tasks()) == before, "broadcast left detached cancellation tasks"
    finally:
        released.set()
        for server, thread in zip((slow, healthy), threads, strict=True):
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


@pytest.mark.asyncio
async def test_orphan_sweep_honours_startup_grace(monkeypatch):
    from packages.telephony import freeswitch_esl as esl
    from services.imvera_media_bridge import main

    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)

    async def api(*args, **kwargs):
        assert sleeps, "ESL sweep started before fresh call setups had their grace period"
        return '{"rows": []}'

    monkeypatch.setattr(main, "_bridge_start_mono", time.monotonic() - 10)
    monkeypatch.setattr(main.asyncio, "sleep", sleep)
    monkeypatch.setattr(esl, "freeswitch_api", api)
    await main._sweep_orphan_channels()
    assert len(sleeps) == 1 and 49 < sleeps[0] <= 50


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", ["object", "list"])
async def test_orphan_sweep_rechecks_live_session_after_await(monkeypatch, shape):
    from packages.telephony import freeswitch_esl as esl
    from services.imvera_media_bridge import callactor, main

    live = {}
    killed = []
    rows = [{"uuid": uuid, "application": "audio_stream"} for uuid in ("orphan", "fresh")]

    async def api(*args, **kwargs):
        return json.dumps({"rows": rows} if shape == "object" else rows)

    async def hangup(uuid):
        killed.append(uuid)
        live["fresh"] = "new-call-registered-during-esl-await"

    monkeypatch.setattr(main, "_bridge_start_mono", time.monotonic() - 61)
    monkeypatch.setattr(callactor, "_live_actors", live)
    monkeypatch.setattr(esl, "freeswitch_api", api)
    monkeypatch.setattr(esl, "hangup_channel", hangup)
    await main._sweep_orphan_channels()
    assert killed == ["orphan"]


@pytest.mark.asyncio
async def test_production_call_limit_rejects_before_binding_or_construction(monkeypatch):
    from services.imvera_media_bridge import callactor

    closed = []

    async def close(**kwargs):
        closed.append(kwargs)

    async def blockers():
        return []

    def resolve(*args):
        pytest.fail("saturated bridge must reject before binding or building another actor")

    monkeypatch.setenv("IMVERA_RUNTIME_MODE", "production")
    monkeypatch.setattr(callactor, "_live_actors", {"existing": "active-call"})
    monkeypatch.setattr(callactor, "inference_blockers", blockers)
    monkeypatch.setattr(callactor, "_resolve_product_mission", resolve)
    await callactor.handle_callactor_ws(SimpleNamespace(close=close), "new-channel")
    assert closed and closed[0]["code"] == 1013
    assert "capacity" in closed[0]["reason"]


@pytest.mark.asyncio
async def test_call_reservation_survives_concurrent_setup_and_releases_on_failure(monkeypatch):
    from services.imvera_media_bridge import callactor

    entered = asyncio.Event()
    release = asyncio.Event()
    closed = []
    live = {}

    async def blockers():
        return []

    async def serve(*args):
        entered.set()
        await release.wait()
        raise RuntimeError("websocket setup failed")

    async def close(**kwargs):
        closed.append(kwargs)

    monkeypatch.setattr(callactor, "inference_blockers", blockers)
    monkeypatch.setattr(callactor, "_production_call_limit", lambda: 1)
    monkeypatch.setattr(callactor, "_live_actors", live)
    monkeypatch.setattr(callactor, "_resolve_product_mission", lambda *a: ("c", "f", "e", None))
    monkeypatch.setattr(callactor, "_serve_callactor_ws", serve)
    ws = SimpleNamespace(close=close)
    task = asyncio.create_task(callactor.handle_callactor_ws(ws, "first"))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await callactor.handle_callactor_ws(ws, "second")
        assert live == {"first": "c"}
        assert closed == [{"code": 1013, "reason": "bridge call capacity reached"}]
    finally:
        release.set()
        with pytest.raises(RuntimeError, match="setup failed"):
            await task
    assert not live


@pytest.mark.asyncio
async def test_pending_readiness_already_owns_slot_and_cancellation_releases_it(monkeypatch):
    from services.imvera_media_bridge import callactor

    entered = asyncio.Event()
    live = {}
    closed = []

    async def blockers():
        entered.set()
        await asyncio.Event().wait()

    async def close(**kwargs):
        closed.append(kwargs)

    monkeypatch.setattr(callactor, "inference_blockers", blockers)
    monkeypatch.setattr(callactor, "_production_call_limit", lambda: 1)
    monkeypatch.setattr(callactor, "_live_actors", live)
    ws = SimpleNamespace(close=close)
    first = asyncio.create_task(callactor.handle_callactor_ws(ws, "first"))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert "first" in live, "readiness await left a connecting channel unowned"
        await asyncio.wait_for(callactor.handle_callactor_ws(ws, "second"), 0.25)
        assert closed == [{"code": 1013, "reason": "bridge call capacity reached"}]
    finally:
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
    assert not live


@pytest.mark.asyncio
async def test_failed_websocket_accept_stops_constructed_actor_and_releases_slot(monkeypatch):
    from services.imvera_media_bridge import callactor

    stopped = []
    live = {}

    async def blockers():
        return []

    async def stop():
        stopped.append(True)

    async def accept():
        raise RuntimeError("client disconnected before accept")

    monkeypatch.setattr(callactor, "inference_blockers", blockers)
    monkeypatch.setattr(callactor, "_production_call_limit", lambda: 1)
    monkeypatch.setattr(callactor, "_live_actors", live)
    monkeypatch.setattr(callactor, "_resolve_product_mission", lambda *a: ("c", "f", "e", None))
    monkeypatch.setattr(callactor, "create_call_record_store", lambda: None)
    monkeypatch.setattr(callactor, "build_call_actor", lambda *a, **kw: SimpleNamespace(stop=stop))
    monkeypatch.setattr(callactor, "_teardown_in_background", lambda *a: None)
    with pytest.raises(RuntimeError, match="disconnected before accept"):
        await callactor.handle_callactor_ws(SimpleNamespace(accept=accept), "channel")
    assert stopped == [True] and not live


@pytest.mark.parametrize("params", [{}, {"mission": "{}"}])
def test_production_cannot_use_lab_family_or_manual_mission(monkeypatch, params):
    from services.imvera_media_bridge import callactor

    monkeypatch.setenv("IMVERA_RUNTIME_MODE", "production")
    monkeypatch.setattr(
        callactor, "create_call_record_store", lambda: pytest.fail("missing product identity"),
    )
    with pytest.raises(callactor.ProductBindingMissing):
        callactor._resolve_product_mission(SimpleNamespace(query_params=params), "missing-id")


@pytest.mark.asyncio
async def test_bridge_health_counts_callactor_sessions(monkeypatch):
    from services.imvera_media_bridge import callactor, main

    async def blockers():
        return []

    monkeypatch.setattr(main, "MODE", "callactor")
    monkeypatch.setattr(main, "_sessions", {})
    monkeypatch.setattr(callactor, "_live_actors", {"channel": "product-call"})
    monkeypatch.setattr(callactor, "inference_blockers", blockers)
    result = await main.ready()
    assert result["active_sessions"] == 1


def test_qwen_dependency_loss_revokes_warm_readiness(monkeypatch):
    from fastapi.testclient import TestClient

    from services.tts import qwen_gguf, worker

    cfg = {"models": {"tts": {"engine": "qwen_gguf"}}}
    monkeypatch.setenv("IMVERA_RUNTIME_MODE", "production")
    monkeypatch.setattr(worker, "_load_config", lambda: cfg)
    monkeypatch.setattr(worker.state, "ready", True)
    monkeypatch.setattr(worker.state, "model_revision", "qwen_gguf:accepted-model")
    monkeypatch.setattr(worker.state, "warmup_error", None)
    monkeypatch.setattr(qwen_gguf, "list_models", lambda **kwargs: [])
    monkeypatch.setattr(qwen_gguf, "list_voices", lambda **kwargs: [])
    restarts = []
    monkeypatch.setattr(worker, "_watchdog", SimpleNamespace(request_restart=restarts.append))
    response = TestClient(worker.app).get("/health/ready")
    assert response.status_code == 503, "warmup cannot prove a disconnected resident still ready"
    assert not worker.state.ready
    assert restarts


@pytest.mark.parametrize("condition", ["healthy", "lost_voice", "changed_model"])
def test_qwen_dependency_identity_and_registry_control_recovery(monkeypatch, condition):
    from fastapi.testclient import TestClient

    from services.tts import qwen_gguf, worker

    monkeypatch.setenv("IMVERA_RUNTIME_MODE", "production")
    monkeypatch.setattr(worker, "_load_config", lambda: {
        "models": {"tts": {"engine": "qwen_gguf"}},
    })
    monkeypatch.setattr(worker.state, "ready", True)
    monkeypatch.setattr(worker.state, "warmup_error", None)
    monkeypatch.setattr(worker.state, "model_revision", "qwen_gguf:accepted-model")
    monkeypatch.setattr(qwen_gguf, "list_models", lambda **kw: [
        "different-model" if condition == "changed_model" else "accepted-model",
    ])
    monkeypatch.setattr(qwen_gguf, "list_voices", lambda **kw: (
        [] if condition == "lost_voice" else ["vera_kseniya"]
    ))
    restarts = []
    monkeypatch.setattr(worker, "_watchdog", SimpleNamespace(request_restart=restarts.append))
    response = TestClient(worker.app).get("/health/ready")
    assert response.status_code == (200 if condition == "healthy" else 503)
    assert bool(restarts) == (condition == "lost_voice")
    if condition == "changed_model":
        assert "operator review" in response.json()["error"]


def test_model_restart_drains_existing_job_before_terminating_worker():
    from services.inference.common import InferenceExecutor, WorkerState
    from services.inference.watchdog import InferenceWatchdog

    executor = InferenceExecutor(max_queue=1)
    state = WorkerState(ready=True)
    release = threading.Event()
    entered = threading.Event()
    fatal = threading.Event()
    consumer_settled = threading.Event()

    def run():
        entered.set()
        release.wait(2)

    job = executor.submit(run)
    guard = InferenceWatchdog(
        executor, state, max_job_s=1, poll_s=0.005, fatal=fatal.set,
        drained=consumer_settled.is_set,
    )
    try:
        assert entered.wait(1)
        guard.request_restart("resident disconnected")
        assert not state.ready and state.warmup_error == "resident disconnected"
        assert not fatal.wait(0.03) and not job.done()
        release.set()
        job.result(timeout=1)
        assert not fatal.wait(0.03), "finished producer is not a finished HTTP consumer"
        consumer_settled.set()
        assert fatal.wait(1)
        assert executor.queue_depth == 0
    finally:
        release.set()
        guard.stop()
        executor._executor.shutdown(wait=True)


def test_recovery_request_really_exits_dedicated_process():
    program = """
import threading
from services.inference.common import InferenceExecutor, WorkerState
from services.inference.watchdog import InferenceWatchdog
executor = InferenceExecutor()
guard = InferenceWatchdog(executor, WorkerState(ready=True), max_job_s=1, poll_s=.01)
guard.request_restart('resident disconnected')
threading.Event().wait()
"""
    result = subprocess.run([sys.executable, "-c", program], capture_output=True, timeout=5)
    assert result.returncode == 70
    assert b"resident disconnected" in result.stderr


def test_readiness_json_slow_trickle_cannot_extend_probe_budget(monkeypatch):
    from services.tts import qwen_gguf

    released = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            return None

        def do_GET(self):
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                packets = [b'{"data": [{"id": "accepted-model"}]}'] + [b" "] * 20
                for packet in packets:
                    self.wfile.write(f"{len(packet):x}\r\n".encode() + packet + b"\r\n")
                    self.wfile.flush()
                    if released.wait(0.02):
                        break
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except OSError:
                return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("IMVERA_QWEN_TTS_URL", f"http://127.0.0.1:{server.server_port}")
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            qwen_gguf.list_models(timeout_s=0.05)
        assert time.monotonic() - started < 0.25
    finally:
        released.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
