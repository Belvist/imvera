"""Regression tests for the audit fixes (concurrency, security, robustness).

Covers:
  * call_agent: per-call lock busy rejection (429), save_upload path
    whitelist, per-hop STT hallucination filtering;
  * tts_server: client_id sanitization, stream-cancellation registry,
    SingleFlight reserve timeout, int16 clipping.
"""
import asyncio
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from conftest_or_paths import RUNTIME_SCRIPTS, SAMPLE_REF  # noqa: E402

sys.path.insert(0, os.path.dirname(_HERE))

import call_agent  # noqa: E402
import tts_server as tts_mod  # noqa: E402
import tts_server as tts_mod  # noqa: E402


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _wav_bytes(samples=1600, rate=16000):
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % samples, *([0] * samples)))
    return buf.getvalue()


def _write_tmp_wav():
    fd, p = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with open(p, "wb") as f:
        f.write(_wav_bytes())
    return p


class _FakeSTT:
    def __init__(self, script):
        self.script = list(script)

    def transcribe_clean(self, wav_path):
        return self.script.pop(0) if self.script else "всё хорошо"


class _GateTTS:
    """TTS stub whose generate() blocks until released — proves the busy check
    rejects a second turn instead of racing the first."""

    def __init__(self):
        self.block = threading.Event()
        self.entered = threading.Event()
        self.count = 0

    def ready(self):
        return True

    def health(self):
        return True, None

    def generate(self, text):
        self.count += 1
        self.entered.set()
        self.block.wait(timeout=10)
        return _wav_bytes()

    def stream(self, text, cancel_event=None, stream_id=None):
        self.count += 1
        self.entered.set()
        self.block.wait(timeout=10)
        yield {"i": 0, "wav_b64": "", "done": True}


class _Args:
    refs = [SAMPLE_REF]
    tts_port_file = None
    tts_port = None
    inference_steps = 6
    no_style = False
    outdir = None
    tmpdir = None


class CallAgentFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.args = _Args()
        cls.args.outdir = os.path.join(_HERE, "_tmp_calls_fix")
        cls.args.tmpdir = os.path.join(_HERE, "_tmp_uploads")
        os.makedirs(cls.args.tmpdir, exist_ok=True)
        cls.serve = call_agent.Serve(cls.args)
        cls.serve.stt = _FakeSTT(["всё хорошо"])
        cls.serve.tts = _GateTTS()
        # Unit-level isolation: the real LLM (in-process or the llm-server)
        # adds 2-7 s of generation per turn and would starve the timing
        # expectations of the busy-guard tests. Scripted fallback replies are
        # exactly what this suite is about.
        cls.serve.llm = None
        cls.port = _free_port()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", cls.port), call_agent.Handler)
        cls.httpd.serve = cls.serve
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        import shutil

        shutil.rmtree(cls.args.outdir, ignore_errors=True)
        shutil.rmtree(cls.args.tmpdir, ignore_errors=True)

    def _post(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else b""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())

    # ---------------- busy guard (429) ----------------
    def test_second_turn_rejected_429_while_busy(self):
        import urllib.error

        self.serve.tts.block.clear()
        self.serve.tts.entered.clear()
        self.serve.stt.script = ["всё хорошо"]
        a = self._post("/calls")
        cid = a["call_id"]
        wav = _write_tmp_wav()

        first = [None]

        def run_first():
            try:
                self._post(f"/calls/{cid}/turn", {"audio": wav})
            except Exception as e:  # noqa: BLE001
                first[0] = e

        t = threading.Thread(target=run_first, daemon=True)
        t.start()
        self.assertTrue(self.serve.tts.entered.wait(5), "turn never started")

        # second concurrent turn -> 429 (HTTPError)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._post(f"/calls/{cid}/turn", {"audio": wav})
        self.assertEqual(cm.exception.code, 429)

        # release, let it finish, verify the flag clears (next turn OK)
        self.serve.tts.block.set()
        t.join(timeout=10)
        self.assertIsNone(first[0], f"first turn failed: {first[0]}")
        ctx = self.serve.get_call(cid)
        self.assertFalse(ctx.turn_in_progress)
        os.remove(wav)

    # ---------------- save_upload whitelist ----------------
    def test_save_upload_rejects_paths_outside_tmp(self):
        secret = os.path.join(os.path.expanduser("~"), ".ssh", "id_rsa")
        # create the sentinel only if missing (never touch the real key)
        created = False
        if not os.path.exists(secret):
            os.makedirs(os.path.dirname(secret), exist_ok=True)
            with open(secret, "w") as f:
                f.write("sentinel")
            created = True
        try:
            path, is_temp = self.serve.save_upload(
                json.dumps({"audio": secret}).encode(), "application/json")
            self.assertIsNone(path, "outside-dir path must be rejected")
        finally:
            if created and os.path.exists(secret):
                os.remove(secret)

    def test_save_upload_stages_tmp_files_into_tmpdir(self):
        wav = _write_tmp_wav()
        try:
            path, is_temp = self.serve.save_upload(
                json.dumps({"audio": wav}).encode(), "application/json")
            self.assertIsNotNone(path, "/tmp wav must be accepted")
            self.assertTrue(is_temp, "staged file must be marked temp")
            self.assertTrue(path.startswith(os.path.realpath(self.args.tmpdir))
                            or path.startswith(self.args.tmpdir))
            os.remove(path)
        finally:
            os.remove(wav)

    # ---------------- per-hop hallucination filter ----------------
    def test_streaming_stt_filters_junk_per_hop(self):
        class JunkEngine:
            def __init__(self):
                self.calls = 0

            def transcribe(self, wav_path):
                self.calls += 1
                # hop 1: whisper junk, hop 2: real speech, hop 3 tail: junk.
                # NOTE: "спасибо"/"до свидания" are NOT junk anymore — they
                # are recovered as real short answers (see _SHORT_ANSWER_MAP).
                return {1: "bye", 2: "мне кажется у меня болит голова",
                        3: "uh"}.get(self.calls, "")

        sstt = call_agent.StreamingSTT(JunkEngine(), sample_rate=16000,
                                       hop_seconds=1.0)
        hop1, interim1 = sstt.feed([100] * 16000)
        self.assertIsNone(hop1, "junk hop 1 must not be confirmed")
        self.assertEqual(interim1, "")
        hop2, interim2 = sstt.feed([100] * 16000)
        self.assertEqual(hop2, "мне кажется у меня болит голова")
        final = sstt.finish()
        self.assertEqual(final, "мне кажется у меня болит голова")


# --------------------------------------------------------------------------- #
# tts_server
# --------------------------------------------------------------------------- #
class TTSServerFixTests(unittest.TestCase):
    def test_client_id_sanitized(self):
        out = tts_mod.sanitize_client_id("../../etc/passwd")
        self.assertNotIn("/", out)
        self.assertNotIn("..", out)
        self.assertIn("etc_passwd", out)
        self.assertEqual(tts_mod.sanitize_client_id(""), "local")
        self.assertEqual(tts_mod.sanitize_client_id("a/b\\c:d"), "a_b_c_d")
        self.assertEqual(tts_mod.sanitize_client_id("ok_id-1.2"), "ok_id-1.2")
        self.assertLessEqual(len(tts_mod.sanitize_client_id("x" * 500)), 64)

    def test_registry_never_escapes_dir(self):
        with tempfile.TemporaryDirectory() as td:
            reg = tts_mod.Registry(td)
            reg.append("../../evil", "user", "hi")
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(td), "evil.jsonl")))
            # file is written with the sanitized name inside conv_dir
            files = os.listdir(os.path.join(td, "conversations"))
            self.assertEqual(len(files), 1)
            self.assertNotIn("..", files[0])
            self.assertEqual(reg.read("../../evil"), reg.read(files[0][:-6]))

    def test_stream_cancel_registry(self):
        w = tts_mod.TTSWorker.__new__(tts_mod.TTSWorker)
        w._streams = {}
        w._streams_lock = threading.Lock()
        ev = w.register_stream("s1")
        self.assertIsInstance(ev, threading.Event)
        self.assertFalse(ev.is_set())
        self.assertTrue(w.cancel_stream("s1"))
        self.assertTrue(ev.is_set())
        self.assertFalse(w.cancel_stream("nope"))
        w.unregister_stream("s1")
        self.assertFalse(w.cancel_stream("s1"))

    def test_singleflight_reserve_times_out(self):
        # queue_size large enough that the waiter actually queues, so the
        # failure mode under test is the reserve TIMEOUT (not queue overflow).
        slot = tts_mod.SingleFlight(queue_size=4, reserve_timeout=0.2)

        with slot.acquire():
            self.assertEqual(slot.metrics()["in_flight"], 1)
            granted = [None]
            t0 = [None]

            def waiter():
                t0[0] = time.time()
                granted[0] = slot._reserve()

            t = threading.Thread(target=waiter, daemon=True)
            t.start()
            t.join(timeout=3)
            self.assertFalse(granted[0], "reserve must time out, not block")
            self.assertGreaterEqual(time.time() - t0[0], 0.18,
                                    "should have waited ~reserve_timeout")
            self.assertGreaterEqual(slot.metrics()["rejected"], 1)

    def test_make_wav_bytes_clips(self):
        import numpy as np

        data = tts_mod.make_wav_bytes(np.array([2.0, -2.0, 0.0]), 16000)
        self.assertIn(b"WAVE", data)
        # no exception = clipped cast worked; decode to verify amplitudes
        import io
        import wave

        with wave.open(io.BytesIO(data), "rb") as w:
            frames = struct.unpack("<3h", w.readframes(3))
        self.assertEqual(frames[0], 32767)
        self.assertEqual(frames[1], -32767)


if __name__ == "__main__":
    unittest.main(verbosity=2)
