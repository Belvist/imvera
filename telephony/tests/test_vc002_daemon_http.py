"""P0-VC-002 / P0-VC-004 HTTP-level regression against a *live* TTS daemon.

Requires the daemon on 127.0.0.1:9600 (as started by start_telephony.command).
Tests are skipped when the daemon or the reference is unavailable so the suite
still runs cleanly offline.

Checks:
* /generate with reference_texts: ok=True, reference_text_source=="client",
  reference_audio_seconds>0, reference_quality present;
* without reference_texts the engine still clones from the audio itself
  (MOSS-TTS-Nano is zero-shot: no transcript is required);
* /stream: frame-based response with reference_text_source in the last frame.
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
from conftest_or_paths import SAMPLE_REF, SAMPLE_REF_TEXT  # noqa: E402

DAEMON = os.environ.get("MOSSTEST_TTS", "http://127.0.0.1:9600")


def _daemon_up():
    try:
        with urllib.request.urlopen(f"{DAEMON}/health", timeout=3) as r:
            obj = json.loads(r.read().decode())
        return bool(obj.get("ready"))
    except Exception:  # noqa: BLE001
        return False


@unittest.skipUnless(_daemon_up(), "TTS daemon not running on 127.0.0.1:9600")
class DaemonReferenceTextHttpTests(unittest.TestCase):
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

    def test_generate_client_text_source(self):
        out = self._post(
            {
                "text": "Здравствуйте. Как вы себя чувствуете?",
                "refs": [SAMPLE_REF],
                "reference_texts": [SAMPLE_REF_TEXT],
                "inference_steps": 6,
            }
        )
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(out.get("reference_text_source"), "client")
        self.assertGreater(out.get("reference_audio_seconds", 0), 1)

    def test_generate_quality_reported(self):
        out = self._post(
            {
                "text": "Скажите, что случилось.",
                "refs": [SAMPLE_REF],
                "reference_texts": [SAMPLE_REF_TEXT],
                "inference_steps": 6,
            }
        )
        self.assertTrue(out.get("ok"), out)
        self.assertIn(out.get("reference_quality"), ("GOOD", "WARNING", "REJECT"))

    def test_no_client_text_clones_from_audio(self):
        # MOSS-TTS-Nano clones zero-shot from the reference audio, so no
        # STT transcript is required when the client omits reference_texts.
        out = self._post(
            {
                "text": "Привет.",
                "refs": [SAMPLE_REF],
                "inference_steps": 6,
            }
        )
        self.assertTrue(out.get("ok"), out)
        self.assertIn(out.get("reference_text_source"), ("audio", "stt"))

    def test_stream_metadata_on_last_frame(self):
        import http.client

        payload = {
            "text": "Скажите, как себя чувствуете.",
            "refs": [SAMPLE_REF],
            "reference_texts": [SAMPLE_REF_TEXT],
            "inference_steps": 6,
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
        self.assertEqual(last.get("reference_text_source"), "client")
        self.assertGreater(last.get("reference_audio_seconds", 0), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)