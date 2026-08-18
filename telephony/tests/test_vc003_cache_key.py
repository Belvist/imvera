"""P0-VC-003 regression: cache key must change when the reference transcript
changes and must stay stable when it does not. Runs pure logic — no model load.
"""
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from conftest_or_paths import RUNTIME_SCRIPTS  # noqa: E402

sys.path.insert(0, RUNTIME_SCRIPTS)

import tts_common  # noqa: E402
from tts_server import TTSWorker  # noqa: E402


def _bare_worker(model_id="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit"):
    """TTSWorker without model load: only the key/reference-logic surfaces."""
    w = TTSWorker.__new__(TTSWorker)
    w.model_id = model_id
    return w


class CacheKeyTests(unittest.TestCase):
    def setUp(self):
        self.refs = [os.path.join(tempfile.gettempdir(), "moss-ref-a.wav")]
        with open(self.refs[0], "wb") as _f:
            _f.write(b"\x00" * 1024)

    def tearDown(self):
        for p in self.refs:
            try:
                os.remove(p)
            except OSError:
                pass

    def test_same_keys_equal(self):
        w = _bare_worker()
        k1 = w._key(self.refs, "SAME TEXT")
        k2 = w._key(self.refs, "SAME TEXT")
        self.assertEqual(k1, k2)

    def test_transcript_change_changes_key(self):
        w = _bare_worker()
        k1 = w._key(self.refs, "текст А")
        k2 = w._key(self.refs, "текст Б")
        self.assertNotEqual(k1, k2)

    def test_no_text_yields_different_windows(self):
        w = _bare_worker()
        k_no = w._key(self.refs, None)
        k_txt = w._key(self.refs, "текст")
        self.assertNotEqual(k_no, k_txt)

    def test_model_change_changes_key(self):
        w1 = _bare_worker("model-A")
        w2 = _bare_worker("model-B")
        self.assertNotEqual(
            w1._key(self.refs, "текст"), w2._key(self.refs, "текст")
        )

    def test_key_stable_for_same_input_across_instances(self):
        w1 = _bare_worker()
        w2 = _bare_worker()
        self.assertEqual(
            w1._key(self.refs, "SOME TEXT"), w2._key(self.refs, "SOME TEXT")
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)