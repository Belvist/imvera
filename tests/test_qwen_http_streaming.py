"""Actual chunked HTTP proves available PCM, deadline and cancellation behavior."""

from __future__ import annotations

import concurrent.futures
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from services.inference.streaming import StreamCancelled
from services.tts import qwen_gguf


@pytest.fixture
def pcm_server(monkeypatch):
    release = threading.Event()
    first = b"\x01\x00" * 8
    later = b"\x02\x00" * 8

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            return None

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "audio/pcm")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                for packet in (first, later):
                    self.wfile.write(f"{len(packet):x}\r\n".encode() + packet + b"\r\n")
                    self.wfile.flush()
                    if packet is first:
                        release.wait(3)
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except OSError:
                # A deadline/cancel test deliberately closes this connection.
                return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("IMVERA_QWEN_TTS_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(qwen_gguf, "_model_id", "controlled-transport-fixture")
    try:
        yield release, first, later
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_short_first_packet_does_not_wait_for_full_network_buffer(pcm_server):
    release, first, later = pcm_server
    stream = qwen_gguf.synthesize_stream("Поняла.", deadline=time.monotonic() + 3)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        first_future = executor.submit(next, stream)
        try:
            assert first_future.result(timeout=1) == first
            assert not release.is_set()
            release.set()
            assert b"".join(stream) == later
        finally:
            release.set()
            first_future.result(timeout=2)
            stream.close()


def test_cancellation_between_packets_closes_instead_of_starting_another_read(pcm_server):
    release, first, _ = pcm_server
    cancelled = threading.Event()
    stream = qwen_gguf.synthesize_stream(
        "Поняла.",
        deadline=time.monotonic() + 3,
        cancelled=cancelled.is_set,
    )
    try:
        assert next(stream) == first
        cancelled.set()
        with pytest.raises(StreamCancelled):
            next(stream)
        assert not release.is_set()
    finally:
        release.set()
        stream.close()


def test_stalled_http_read_is_bounded_by_request_budget(pcm_server):
    release, first, _ = pcm_server
    stream = qwen_gguf.synthesize_stream("Поняла.", deadline=time.monotonic() + 0.15)
    started = time.monotonic()
    try:
        assert next(stream) == first
        with pytest.raises((RuntimeError, TimeoutError)):
            next(stream)
        assert time.monotonic() - started < 1
        assert not release.is_set()
    finally:
        release.set()
        stream.close()
