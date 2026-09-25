"""Replica pool: round-robin + failover across worker URLs."""

from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from packages.contracts.providers import ProviderUnavailable
from packages.contracts.semantic import TurnContext
from services.llm.http_provider import HttpLLMProvider
from services.providers.replica_pool import ReplicaPool, is_retryable_status, split_urls
from services.stt.http_provider import HttpSTTProvider
from services.tts.http_provider import HttpTTSProvider

PAYLOAD = {
    "dialogue_act": "answer",
    "control": "none",
    "consent_answer": "not_applicable",
    "answers_pending_question": True,
    "needs_clarification": False,
}


class _Handler(BaseHTTPRequestHandler):
    mode = "ok"
    hits = 0

    def log_message(self, *_a):
        pass

    def _send(self, code: int, body: bytes, ctype="application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        type(self).hits += 1
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        if self.path == "/v1/transcribe":
            if self.mode == "busy":
                self._send(503, b'{"error":"queue full"}')
            elif self.mode == "verdict":
                self._send(422, b'{"error":"bad shape"}')
            else:
                self._send(200, json.dumps({"text": "хорошо", "asr_quality": "GOOD"}).encode())
        elif self.path == "/v1/synthesize":
            if self.mode == "busy":
                self._send(503, b'{"error":"queue full"}')
            else:
                pcm = base64.b64encode(b"\x01\x00" * 320).decode()
                lines = (
                    json.dumps({"pcm_b64": pcm, "sample_rate": 16000}) + "\n"
                    + json.dumps({"done": True}) + "\n"
                )
                self._send(200, lines.encode())
        elif self.path == "/v1/interpret":
            if self.mode == "busy":
                self._send(503, b'{"error":"queue full"}')
            else:
                self._send(
                    200,
                    json.dumps({"payload": PAYLOAD, "request_id": "r"}).encode(),
                )
        else:
            self._send(404, b"{}")


def _serve(mode: str):
    handler = type(f"H_{mode}_{time.monotonic_ns()}", (_Handler,), {"mode": mode, "hits": 0})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, handler


def _ctx() -> TurnContext:
    return TurnContext(
        call_id="p", turn_id=1, utterance_id="u", state_version=1,
        raw_text="хорошо", asr_quality="GOOD", pending_question_id=None,
        pending_question="Как дела?", pending_question_delivery="complete",
    )


def test_pool_rotates_start() -> None:
    pool = ReplicaPool(["a", "b", "c"])
    assert pool.order() == ["a", "b", "c"]
    assert pool.order() == ["b", "c", "a"]
    assert pool.order() == ["c", "a", "b"]


def test_split_urls() -> None:
    assert split_urls("http://h:1") == ["http://h:1"]
    assert split_urls("http://h:1, http://h:2/") == ["http://h:1", "http://h:2"]
    assert is_retryable_status(503) and is_retryable_status(429)
    assert not is_retryable_status(422) and not is_retryable_status(200)


def test_stt_failover_busy_to_healthy() -> None:
    async def scenario() -> None:
        busy, h_busy = _serve("busy")
        ok_srv, h_ok = _serve("ok")
        try:
            p = HttpSTTProvider(
                f"http://127.0.0.1:{busy.server_port},"
                f"http://127.0.0.1:{ok_srv.server_port}"
            )
            res = await p.transcribe_final(
                b"\x00" * 640, 16000, call_id="c", turn_id=1,
                deadline=time.monotonic() + 30,
            )
            assert res.text == "хорошо"
            assert h_busy.hits >= 1 and h_ok.hits >= 1
        finally:
            busy.shutdown()
            ok_srv.shutdown()

    asyncio.run(scenario())


def test_stt_no_retry_on_verdict() -> None:
    async def scenario() -> None:
        bad, h_bad = _serve("verdict")
        ok_srv, h_ok = _serve("ok")
        try:
            p = HttpSTTProvider(
                f"http://127.0.0.1:{bad.server_port},"
                f"http://127.0.0.1:{ok_srv.server_port}"
            )
            with pytest.raises(ProviderUnavailable, match="422"):
                await p.transcribe_final(
                    b"\x00" * 640, 16000, call_id="c", turn_id=1,
                    deadline=time.monotonic() + 30,
                )
            assert h_ok.hits == 0
        finally:
            bad.shutdown()
            ok_srv.shutdown()

    asyncio.run(scenario())


def test_stt_all_down_raises() -> None:
    async def scenario() -> None:
        p = HttpSTTProvider("http://127.0.0.1:1,http://127.0.0.1:2")
        with pytest.raises(ProviderUnavailable):
            await p.transcribe_final(
                b"\x00" * 640, 16000, call_id="c", turn_id=1,
                deadline=time.monotonic() + 30,
            )

    asyncio.run(scenario())


def test_tts_failover_before_first_chunk() -> None:
    async def scenario() -> None:
        busy, _ = _serve("busy")
        ok_srv, _ = _serve("ok")
        try:
            p = HttpTTSProvider(
                f"http://127.0.0.1:{busy.server_port},"
                f"http://127.0.0.1:{ok_srv.server_port}"
            )
            chunks = [
                ch async for ch in p.synthesize(
                    "Привет", call_id="c", generation_id="g",
                    phrase_id="p", deadline=time.monotonic() + 30,
                )
            ]
            assert len(chunks) == 1 and chunks[0].pcm_s16le == b"\x01\x00" * 320
        finally:
            busy.shutdown()
            ok_srv.shutdown()

    asyncio.run(scenario())


def test_llm_failover_dead_port_to_healthy() -> None:
    async def scenario() -> None:
        ok_srv, _ = _serve("ok")
        try:
            p = HttpLLMProvider(
                f"http://127.0.0.1:1,http://127.0.0.1:{ok_srv.server_port}"
            )
            res = await p.interpret_turn(_ctx(), deadline=time.monotonic() + 30)
            assert res.payload.dialogue_act == "answer"
        finally:
            ok_srv.shutdown()

    asyncio.run(scenario())
