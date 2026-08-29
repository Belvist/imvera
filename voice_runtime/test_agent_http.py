"""Agent-client contract tests (FIXES_PLAN P2, 2026-08-29).

Covers the turn_stream wire contract against a real HTTP server that speaks
the production shape (chunked body with length-prefixed JSON frames):
  * a 200 turn_stream must report SUCCESS even though the body is NOT a
    single JSON document (the old `_json` made every success a "bad JSON");
  * 429/404 rejections must be distinguishable (busy / swept call) and
    surface as AgentError with the server's error text;
  * create_call must forward caller_id (the agenda/family hook);
  * CallSession._stream_done must unblock streaming on a hard failure.
"""
import json
import os
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_http import AgentClient, AgentError  # noqa: E402
from call_session import CallSession  # noqa: E402


def chunked_frames(frames):
    """Encode list[dict] as the production chunked length-prefixed stream."""
    out = b""
    for f in frames:
        payload = json.dumps(f, ensure_ascii=False).encode("utf-8")
        out += (len(payload)).to_bytes(4, "big") + payload
    return (b"%X\r\n" % len(out)) + out + b"\r\n0\r\n\r\n"


class _Handler(BaseHTTPRequestHandler):
    server_version = "MossTest"

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(ln) if ln else b""
        try:
            payload = json.loads(body) if body else {}
        except ValueError:
            payload = {}
        cfg = self.server.cfg
        if self.path == "/calls":
            cfg["last_create"] = payload
            self._send(200, json.dumps({"call_id": "call-123"}).encode())
            return
        if self.path == "/say":
            self._send(200, json.dumps(
                {"wav_path": "/tmp/mossvoice/greet.wav"}).encode())
            return
        if self.path == "/ready":
            self._send(200, json.dumps({"ready": True}).encode())
            return
        if self.path.endswith("/turn_stream"):
            mode = cfg.get("mode", "ok")
            if mode == "ok":
                data = chunked_frames([
                    {"type": "interim", "transcript": "привет", "final":
                     False},
                    {"type": "done", "transcript": "привет", "reply":
                     "Здравствуйте!"},
                ])
                self.send_response(200)
                self.send_header("Content-Type",
                                 "application/octet-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                self.wfile.write(data)
                return
            if mode == "busy":
                self._send(429, json.dumps(
                    {"ok": False, "error": "call busy"}).encode())
                return
            if mode == "gone":
                self._send(404, json.dumps(
                    {"ok": False, "error": "call not found"}).encode())
                return
            self._send(500, json.dumps({"ok": False,
                                        "error": "boom"}).encode())
            return
        self._send(404, json.dumps({"ok": False, "error": "nf"}).encode())


class AgentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.httpd.cfg = {}
        cls.thread = threading.Thread(target=cls.httpd.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.port = cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def setUp(self):
        self.httpd.cfg = {}
        self.client = AgentClient("127.0.0.1", self.port, timeout=5)

    def _wait(self, ev):
        ev.wait(5)
        self.assertTrue(ev.is_set(), "callback never fired")

    def test_successful_turn_stream_is_not_bad_json(self):
        done = threading.Event()
        results = {}
        self.client.turn_stream(
            "call-123", ["/tmp/x.wav"], "/tmp/seg",
            on_done=lambda ok, info: (results.update(ok=ok, info=info),
                                      done.set()))
        self._wait(done)
        self.assertTrue(results["ok"], "200 frame stream must be success: "
                                       "%r" % results.get("info"))

    def test_busy_rejection_is_false_and_distinct(self):
        self.httpd.cfg["mode"] = "busy"
        done = threading.Event()
        results = {}
        self.client.turn_stream(
            "call-123", ["/tmp/x.wav"], "/tmp/seg",
            on_done=lambda ok, info: (results.update(ok=ok, info=info),
                                      done.set()))
        self._wait(done)
        self.assertFalse(results["ok"])
        self.assertIn("429", results["info"])

    def test_gone_rejection_is_false_and_distinct(self):
        self.httpd.cfg["mode"] = "gone"
        done = threading.Event()
        results = {}
        self.client.turn_stream(
            "call-123", ["/tmp/x.wav"], "/tmp/seg",
            on_done=lambda ok, info: (results.update(ok=ok, info=info),
                                      done.set()))
        self._wait(done)
        self.assertFalse(results["ok"])
        self.assertIn("404", results["info"])

    def test_create_call_forwards_caller_id(self):
        call_id = self.client.create_call({"caller_id": "+79001234567"})
        self.assertEqual(call_id, "call-123")
        self.assertEqual(self.httpd.cfg["last_create"].get("caller_id"),
                         "+79001234567")

    def test_create_call_without_caller_id(self):
        call_id = self.client.create_call()
        self.assertEqual(call_id, "call-123")
        self.assertNotIn("caller_id", self.httpd.cfg["last_create"])


class StreamDoneUnblockTests(unittest.TestCase):
    """CallSession._stream_done must release the streaming flag on a hard
    turn_stream failure — otherwise the session goes deaf forever."""

    class _Noop:
        def __getattr__(self, name):
            return lambda *a, **k: None

    def _session(self, turn_no=1):
        s = CallSession("uuid", self._Noop(), self._Noop(), "/tmp/x",
                        caller_id=None, log=lambda m: None)
        s.streaming = True
        s.suppress = True
        s.segdir = "/tmp/seg"
        s.turn_no = turn_no
        return s

    def test_failure_of_current_turn_unblocks(self):
        s = self._session(turn_no=1)
        s._stream_done(False, "turn_stream HTTP 429: call busy", turn_no=1)
        self.assertFalse(s.streaming)
        self.assertFalse(s.suppress)
        self.assertIsNone(s.segdir)

    def test_success_keeps_streaming(self):
        # success is resolved by done.json in _pump_segments, not here
        s = self._session(turn_no=1)
        s._stream_done(True, "", turn_no=1)
        self.assertTrue(s.streaming)

    def test_stale_failure_does_not_kill_newer_turn(self):
        s = self._session(turn_no=2)   # current turn is 2
        s._stream_done(False, "old 429", turn_no=1)   # stale callback
        self.assertTrue(s.streaming, "stale failure must not unblock new turn")


if __name__ == "__main__":
    unittest.main(verbosity=2)