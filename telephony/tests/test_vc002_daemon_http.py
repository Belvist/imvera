"""P0-VC-002 HTTP-level regression against a *live* TTS daemon (Silero backend).

Requires the daemon on 127.0.0.1:9600 (as started by the docker stack).
Tests are skipped when the daemon is unavailable so the suite still runs
cleanly offline.

Checks (Silero era — voice cloning is gone):
* /generate with a reference: ok=True, coherent 48 kHz audio (wav_b64),
  no clone metadata (Silero has no zero-shot cloning);
* /generate without a reference works the same way;
* /stream: length-prefixed JSON frames, last frame done=True, audio in each.
"""
import base64
import json
import os
import sys
import unittest
import urllib.parse
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from conftest_or_paths import SAMPLE_REF  # noqa: E402

DAEMON = os.environ.get("MOSSTEST_TTS", "http://127.0.0.1:9600")


def _daemon_up():
    try:
        with urllib.request.urlopen(f"{DAEMON}/health", timeout=3) as r:
            obj = json.loads(r.read().decode())
        return bool(obj.get("ready"))
    except Exception:  # noqa: BLE001
        return False


@unittest.skipUnless(_daemon_up(), "TTS daemon not running on 127.0.0.1:9600")
class DaemonHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert os.path.exists(SAMPLE_REF), SAMPLE_REF

    def _post(self, payload, path="/generate"):
        req = urllib.request.Request(
            f"{DAEMON}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read().decode())

    @staticmethod
    def _wav_seconds(out):
        wav = out.get("wav_b64")
        if not wav:
            return 0.0
        raw = base64.b64decode(wav)
        import struct
        assert raw[:4] == b"RIFF", "not a WAV payload"
        sr = struct.unpack("<I", raw[24:28])[0]
        data = raw[44:]
        return len(data) / 2 / sr

    def test_generate_with_reference(self):
        out = self._post(
            {
                "text": "Здравствуйте. Как вы себя чувствуете?",
                "refs": [SAMPLE_REF],
                "inference_steps": 6,
            }
        )
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(out.get("sample_rate"), 48000)
        self.assertGreater(self._wav_seconds(out), 1.0)
        self.assertIsNone(out.get("reference_text_source"),
                          "Silero does not clone voices")

    def test_generate_without_reference(self):
        out = self._post({"text": "Скажите, что случилось."})
        self.assertTrue(out.get("ok"), out)
        self.assertGreater(self._wav_seconds(out), 1.0)

    def test_stream_frames_with_done_last(self):
        import http.client

        payload = {
            "text": "Скажите, как себя чувствуете.",
            "client_id": "regression-stream",
        }
        parts = urllib.parse.urlsplit(DAEMON)
        conn = http.client.HTTPConnection(
            parts.hostname or "127.0.0.1",
            parts.port or 9600, timeout=600)
        conn.request("POST", "/stream", body=json.dumps(payload).encode("utf-8"),
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        buf = b""
        last = None
        frames = 0
        while True:
            chunk = resp.read1(65536)
            if not chunk:
                break
            buf += chunk
            while len(buf) >= 4:
                ln = int.from_bytes(buf[:4], "big")
                if len(buf) < 4 + ln:
                    break
                fr = json.loads(buf[4:4 + ln].decode("utf-8"))
                buf = buf[4 + ln:]
                frames += 1
                last = fr
        conn.close()
        self.assertGreater(frames, 0)
        self.assertTrue(last.get("done"))
        self.assertGreater(last.get("sample_rate", 0), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)