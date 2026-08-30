"""P0-SESSION-001 regression: isolated call contexts.

Two concurrent calls must NOT share or reset each other's Agent state or
Recorder turns. New API: POST /calls -> call_id, POST /calls/{id}/turn,
POST /calls/{id}/end, GET /calls. Legacy /new, /turn keep working.

Runs the real Serve (with a stubbed STT/placeholder TTS daemon client so no
model load is required) and talks to it over HTTP on an ephemeral port.
"""
import json
import os
import socket
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from conftest_or_paths import SAMPLE_REF  # noqa: E402

sys.path.insert(0, os.path.dirname(_HERE))
import call_agent  # noqa: E402


class _FakeSTT:
    def __init__(self, script):
        """script maps a transcript -> next transcript (stateful)."""
        self.script = list(script)

    def transcribe_clean(self, wav_path):
        return self.script.pop(0) if self.script else "всё хорошо"

    def transcribe_with_confidence(self, wav_path):
        # Qwen3 honest: None -> unknown (U9). Fake must return high confidence
        # so legacy session tests expecting ok/attention keep passing.
        from core.safety_engine import Observation  # noqa
        # Local tiny result mimicking orchestrator's STT result shape
        class R:
            def __init__(self, text):
                self.text = text
                self.confidence = 0.9
                self.segments = ()
        return R(self.transcribe_clean(wav_path))


class _FakeTTS:
    def __init__(self):
        pass

    def ready(self):
        return True

    def health(self):
        return True, None

    def generate(self, text):
        import struct
        # 0.1 s of 16 kHz silence PCM wrapped in a WAV
        import io
        import wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(struct.pack("<%dh" % 1600, *([0] * 1600)))
        return buf.getvalue()

    def stream(self, text):
        yield {"i": 0, "wav_b64": "", "done": True}


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class _Args:
    refs = [SAMPLE_REF]
    tts_port_file = None
    tts_port = None
    inference_steps = 6
    no_style = False
    outdir = None


def _wav_body():
    import struct
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<%dh" % 1600, *([0] * 1600)))
    return buf.getvalue()


def _write_tmp_wav():
    import os
    import tempfile

    fd, p = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with open(p, "wb") as f:
        f.write(_wav_body())
    return p


class SessionIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.args = _Args()
        cls.args.outdir = os.path.join(_HERE, "_tmp_calls")
        cls.serve = call_agent.Serve(cls.args)
        cls.serve.stt = _FakeSTT(["всё хорошо"])
        cls.serve.tts = _FakeTTS()
        cls.port = _free_port()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", cls.port), call_agent.Handler)
        cls.httpd.serve = cls.serve
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()

    def setUp(self):
        # each test controls the scripted STT transcript sequence from scratch
        self.serve.stt.script = list(self._stt_script())

    def _stt_script(self):
        return ["всё хорошо"]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        import shutil

        shutil.rmtree(cls.args.outdir, ignore_errors=True)

    def _post(self, path, body=None, ctype="application/json"):
        data = body if isinstance(body, (bytes, bytearray)) else (
            json.dumps(body).encode() if body is not None else b""
        )
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={"Content-Type": ctype} if data else {},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())

    def _post_turn(self, path):
        wav = _write_tmp_wav()
        try:
            return self._post(path, body={"audio": wav})
        finally:
            try:
                os.remove(wav)
            except OSError:
                pass

    def _get(self, path):
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}{path}", timeout=60
        ) as r:
            return json.loads(r.read().decode())

    def test_two_calls_do_not_share_state(self):
        self.serve.stt.script = ["плохо", "всё хорошо", "помощь нужна"]
        a = self._post("/calls")
        b = self._post("/calls")
        self.assertNotEqual(a["call_id"], b["call_id"])

        # call A: first turn -> "плохо" (agent moves step 0->1, attention note)
        t1 = self._post_turn(f"/calls/{a['call_id']}/turn")
        self.assertEqual(t1["transcript"], "плохо")
        self.assertEqual(t1["outcome"]["status"], "attention")

        # call B: fresh agent must still be starting; its first answer does
        # NOT carry A's attention note
        tb1 = self._post_turn(f"/calls/{b['call_id']}/turn")
        self.assertEqual(tb1["transcript"], "всё хорошо")
        self.assertEqual(tb1["outcome"]["status"], "ok")
        self.assertNotIn("плохое самочувствие", tb1["outcome"]["notes"])

        # advance A further; A's state intact even though B ran in between
        t2 = self._post_turn(f"/calls/{a['call_id']}/turn")
        self.assertEqual(t2["transcript"], "помощь нужна")
        # A step1 answer "всё хорошо" + step2 "помощь нужна" -> attention note
        self.assertEqual(t2["outcome"]["status"], "attention")

    def test_call_id_reported_and_end_returns_outcome(self):
        a = self._post("/calls")
        self._post_turn(f"/calls/{a['call_id']}/turn")
        end = self._post(f"/calls/{a['call_id']}/end")
        self.assertTrue(end["finished"])
        self.assertIn("outcome", end)
        # ended call is gone from listing
        calls = self._get("/calls")["calls"]
        self.assertNotIn(a["call_id"], [c["call_id"] for c in calls])

    def test_legacy_new_and_turn_still_work(self):
        n = self._post("/new")
        self.assertTrue(n.get("ok"))
        self.assertIn("call_id", n)
        t = self._post_turn("/turn")
        self.assertTrue(t.get("ok"))
        self.assertIn("call_id", t)

    def test_unknown_call_404(self):
        import urllib.error

        with self.assertRaises(urllib.error.HTTPError):
            self._post("/calls/doesnotexist/turn")

    def test_json_audio_ref_not_deleted(self):
        """REG-001: the handler must only remove temp waveforms it created;
        a JSON-referenced file stays on disk after a turn (a previous shared
        `finally: os.remove(...)` deleted it and broke the /calls/<id>/turn
        cycle for real call loops)."""
        wav = _write_tmp_wav()
        try:
            a = self._post("/calls")
            t = self._post(f"/calls/{a['call_id']}/turn", body={"audio": wav})
            self.assertTrue(t.get("ok"))
            self.assertTrue(os.path.exists(wav), "JSON-referenced wav was deleted by handler")
        finally:
            try:
                os.remove(wav)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)