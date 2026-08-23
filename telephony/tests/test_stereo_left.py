"""Regression: record_stereo (2026-08-22) — caller audio survives as the
LEFT channel only. FreeSWITCH uuid_record with record_stereo writes
LEFT = caller (read stream), RIGHT = played audio (Vera). Every consumer
(VAD gate, turn concat, ESL reader) must drop RIGHT — otherwise Vera's
playback leaks into STT and gets transcribed as user speech."""
import os
import struct
import sys
import tempfile
import unittest
import wave

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from conftest_or_paths import RUNTIME_SCRIPTS  # noqa: E402

sys.path.insert(0, RUNTIME_SCRIPTS)
sys.path.insert(0, os.path.dirname(_HERE))


def _stereo_wav(path, left, right, rate=8000):
    interleaved = [v for pair in zip(left, right) for v in pair]
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(interleaved), *interleaved))


class ConcatStereoLeftTests(unittest.TestCase):
    def test_concat_stereo_becomes_mono_left(self):
        from core.orchestrator import Serve

        serve = Serve.__new__(Serve)
        serve.tmpdir = tempfile.mkdtemp(prefix="stereo_")
        left = [100, -200, 300, -400] * 100
        vera = [9000, -9000, 9000, -9000] * 100
        paths = []
        for _ in range(2):
            fd, p = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            _stereo_wav(p, left, vera)
            paths.append(p)
        try:
            out = serve._concat_chunks(paths)
            with wave.open(out) as w:
                self.assertEqual(w.getnchannels(), 1)
                self.assertEqual(w.getnchannels() * w.getnframes(),
                                 len(left) * 2)
                frames = w.readframes(w.getnframes())
            vals = struct.unpack("<%dh" % (len(frames) // 2), frames)
            self.assertEqual(list(vals), left * 2)   # caller kept exactly
        finally:
            for p in paths:
                try:
                    os.remove(p)
                except OSError:
                    pass


class EchoGuardTests(unittest.TestCase):
    def setUp(self):
        from core.orchestrator import Serve

        self.guard = Serve._looks_like_echo

    def test_vera_phrase_is_echo(self):
        reply = ("Слушай, а что именно вы имеете в виду? "
                 "Расскажите, я записываю для близких.")
        self.assertTrue(self.guard("что именно вы имеете в виду", reply))
        unclear_reply = ("Простите, если не ясно — уточните, "
                         "чего именно вы хотите узнать?")
        self.assertTrue(self.guard(
            "ну не ясно, а чём именно, то вы хотите узнать", unclear_reply))

    def test_genuine_answers_pass(self):
        reply = "Как ваша голова сейчас? Таблетка помогла?"
        self.assertFalse(self.guard("да, всё хорошо, спасибо", reply))
        self.assertFalse(self.guard("голова болит", reply))       # short
        self.assertFalse(self.guard("таблетка помогла", reply))   # 2 tokens
        self.assertFalse(self.guard("", reply))
        self.assertFalse(self.guard("всё хорошо", None))

    def test_partial_overlap_with_new_info_passes(self):
        reply = "Расскажите, что вы хотели узнать"
        self.assertFalse(self.guard(
            "я хотела узнать про таблетки на завтра", reply))


if __name__ == "__main__":
    unittest.main(verbosity=2)
