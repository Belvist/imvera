"""MediaAdapter contract tests (read.md G2, 2026-08-29).

The realtime VAD/turn loop must never depend on WHICH transport delivers
media. Every adapter (the dev uuid_record tail-reader today; the future ESL
media-bug / WebSocket / RTP source) implements the same contract:
frames_in(), rate, audio_bytes(), broken, close(). A broken source emits NO
frames — it once made the assistant "hear" hallucinated speech.
"""
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from media_adapter import MediaAdapter, NullMedia  # noqa: E402
from media_tap import LiveWavReader  # noqa: E402


def _mono_wav(path, samples, rate=16000):
    """int16 samples -> valid mono WAV on disk."""
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))


def _stereo_wav(path, left, right, rate=16000):
    import wave
    import itertools
    inter = list(itertools.chain(*zip(left, right)))
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(inter), *inter))


class MediaAdapterContractTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="mossmedia-")

    def _wav(self, name, samples, **kw):
        p = os.path.join(self.dir, name)
        _mono_wav(p, samples, **kw)
        return p

    def test_null_media_never_broken_and_empty(self):
        n = NullMedia()
        self.assertFalse(n.broken)
        self.assertEqual(n.frames_in(), [])
        self.assertEqual(n.audio_bytes(), 0)
        n.close()  # must not raise

    def test_valid_mono_is_adaptable(self):
        p = self._wav("m.wav", [100, 200, 300] * 10)
        r = LiveWavReader(p)
        frames = r.frames_in()
        self.assertFalse(r.broken)
        self.assertEqual(frames, [100, 200, 300] * 10)
        self.assertEqual(r.audio_bytes(), 60)  # payload only (30 samples * 2B)

    def test_stereo_left_only(self):
        left = [i for i in range(20)]
        right = [9999] * 20
        p = os.path.join(self.dir, "s.wav")
        _stereo_wav(p, left, right)
        r = LiveWavReader(p)
        frames = r.frames_in()
        self.assertFalse(r.broken)
        self.assertEqual(frames, left, "RIGHT channel must never leak")

    def test_8k_resampled_to_16k(self):
        p = self._wav("r8.wav", [10, 20, 30, 40], rate=8000)
        r = LiveWavReader(p)
        frames = r.frames_in()
        self.assertEqual(len(frames), 8)   # 8k * 2 = 16k
        self.assertEqual(frames[0], 10)

    def test_broken_header_yields_no_frames(self):
        p = os.path.join(self.dir, "garbage.wav")
        with open(p, "wb") as f:
            f.write(b"\x00" * 44)   # the 44-byte failed-record_stereo header
        r = LiveWavReader(p)
        self.assertEqual(r.frames_in(), [])
        self.assertTrue(r.broken)

    def test_partial_trailing_frame_buffered(self):
        p = self._wav("part.wav", [1, 2, 3] * 5)
        r = LiveWavReader(p)
        with open(p, "ab") as f:
            f.write(b"\xff")          # 1 stray byte -> half a sample
        frames = r.frames_in()
        self.assertEqual(len(frames), 15)  # complete frames only, no splice
        r.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)