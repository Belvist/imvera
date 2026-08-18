"""Regression tests for the audit fixes (concurrency, security, robustness).

Covers:
  * call_agent: per-call lock busy rejection (429), save_upload path
    whitelist, per-hop STT hallucination filtering;
  * tts_server: client_id sanitization, stream-cancellation registry,
    SingleFlight reserve timeout, int16 clipping;
  * tg_server: Telegram initData HMAC validation, VAD chunk timing,
    TXPipeline per-generation cancel capture.
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
sys.path.insert(0, os.path.join(_HERE, "..", "tg"))

# NOTE: import order matters — tts_server.py/call_agent.py insert the
# runtime/scripts dir at sys.path[0] on import, which contains stale synced
# copies of the other modules. Import the telephony originals FIRST.
import tg_server  # noqa: E402
import call_agent  # noqa: E402
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
                # hop 1: whisper junk, hop 2: real speech, hop 3 tail: junk
                return {1: "спасибо", 2: "мне кажется у меня болит голова",
                        3: "bye"}.get(self.calls, "")

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


# --------------------------------------------------------------------------- #
# tg_server
# --------------------------------------------------------------------------- #
class TGServerFixTests(unittest.TestCase):
    def test_validate_init_data_valid_and_invalid(self):
        import hashlib
        import hmac
        import urllib.parse

        token = "12345:TEST_TOKEN"

        def make_init_data(user_id=42, auth_date=1700000000, query_id="abc"):
            fields = {"auth_date": str(auth_date), "query_id": query_id,
                      "user": json.dumps({"id": user_id, "first_name": "A"})}
            data_check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
            secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
            h = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
            fields["hash"] = h
            return urllib.parse.urlencode(fields)

        good = make_init_data()
        self.assertTrue(tg_server.validate_init_data(good, token))
        # tampered field
        bad = good.replace("first_name%22%3A+%22A%22", "first_name%22%3A+%22B%22")
        self.assertFalse(tg_server.validate_init_data(bad, token))
        self.assertFalse(tg_server.validate_init_data("", token))
        self.assertFalse(tg_server.validate_init_data(None, token))
        self.assertFalse(tg_server.validate_init_data("hash=deadbeef", token))

    def test_vad_chunk_ms_timing(self):
        vad = tg_server.VAD()
        # 1s of real audio delivered as ONE 1000 ms chunk: without the
        # chunk_ms fix the VAD would count only CHUNK_MS (30 ms) of speech.
        speech = [3000] * 16000
        for _ in range(3):
            vad.feed([0] * 16000, chunk_ms=1000.0)
        vad.feed(speech, chunk_ms=1000.0)
        # silence tail closes the turn; speech_ms was 1000 >= MIN_SPEECH_MS
        turn = None
        for _ in range(5):
            turn, _ = vad.feed([0] * 16000, chunk_ms=1000.0)
            if turn:
                break
        self.assertIsNotNone(turn, "1 s of speech must close a turn")

    def test_txpipeline_cancel_event_captured_per_generation(self):
        """barge-in after start_turn must cancel the RUNNING generation via
        the event its producer actually holds (AUDIT A2)."""
        seen_events = []

        class Bridge:
            def cancel_stream(self):
                pass

            def turn_stream(self, pcm, rate=16000, cancel_event=None):
                seen_events.append(cancel_event)
                i = 0
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        yield {"done": True, "aborted": True}
                        return
                    yield {"i": i, "wav_b64": "AAAA"}
                    i += 1

        sent = []

        async def send(p):
            sent.append(p)

        tx = tg_server.TXPipeline(Bridge(), send)

        async def scene():
            tx.start_turn([31] * 100)
            await asyncio.sleep(0.1)
            first_ev = seen_events[0]
            tx.barge_in()          # must set the SAME event the producer sees
            await asyncio.sleep(0.3)
            return first_ev

        first_ev = asyncio.new_event_loop().run_until_complete(scene())
        self.assertIsNotNone(first_ev)
        self.assertTrue(first_ev.is_set(),
                        "producer's captured event must be set by barge_in")
        self.assertTrue(any(p.get("aborted") for p in sent))

    def test_agent_bridge_pcm_to_wav_bytes_in_memory(self):
        data = tg_server.pcm_to_wav_bytes([0] * 800, 16000)
        self.assertIn(b"WAVE", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
