"""P0-REALTIME-CORE step 11: streaming (incremental) STT.

Whisper decodes whole clips, so StreamingSTT approximates a true stream by
decoding non-overlapping hops of the incoming PCM: a confirmed hop text is
produced as soon as HOP_SECONDS of new audio arrived, interim text is the
running concatenation, and finish() returns the authoritative whole-turn
transcript. These tests use a fake engine to verify the windowing logic
without a real model.
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from call_agent import (  # noqa: E402
    STT_HOP_SECONDS,
    StreamingSTT,
)


class _FakeEngine:
    """Mimics STTEngine.transcribe(wav_path) -> str.

    We cannot easily decode the WAV in the test, so we just return a
    deterministic token based on the hop index recorded via a side channel:
    the caller passes samples; we count how many distinct "windows" were seen
    by tracking the audio length through a class-level counter.
    """

    def __init__(self):
        self.decodes = 0

    def transcribe(self, wav_path):
        self.decodes += 1
        return f"token{self.decodes}"


class StreamingSTTTests(unittest.TestCase):
    def test_hops_are_confirmed_as_audio_arrives(self):
        eng = _FakeEngine()
        sstt = StreamingSTT(eng, sample_rate=16000, hop_seconds=1.0)
        # 1 second of audio = exactly one hop (16000 samples)
        hop, interim = sstt.feed([100] * 16000)
        self.assertEqual(hop, "token1")
        self.assertEqual(interim, "token1")
        # no new hop yet (only 0.5s more) -> hop text None, interim unchanged
        hop2, interim2 = sstt.feed([100] * 8000)
        self.assertIsNone(hop2)
        self.assertEqual(interim2, "token1")
        # another 0.5s completes the second hop
        hop3, interim3 = sstt.feed([100] * 8000)
        self.assertEqual(hop3, "token2")
        self.assertEqual(interim3, "token1 token2")

    def test_tail_audio_is_not_lost(self):
        eng = _FakeEngine()
        sstt = StreamingSTT(eng, sample_rate=16000, hop_seconds=1.0)
        sstt.feed([100] * 16000)  # hop 1
        # a short tail (0.4s) is below one full hop
        sstt.feed([100] * 6400)
        final = sstt.finish()
        # finish decodes the retained tail -> extra decode happens
        self.assertTrue(final, "finish must return a transcript")
        self.assertEqual(eng.decodes, 2)  # hop1 + tail decode

    def test_finish_returns_clean_final(self):
        eng = _FakeEngine()
        sstt = StreamingSTT(eng, sample_rate=16000, hop_seconds=1.0)
        sstt.feed([100] * 16000)
        sstt.feed([100] * 16000)
        final = sstt.finish()
        self.assertIsNotNone(final)
        self.assertIsInstance(final, str)

    def test_no_hop_until_window_fills(self):
        eng = _FakeEngine()
        sstt = StreamingSTT(eng, sample_rate=16000, hop_seconds=2.0)
        hop, _ = sstt.feed([100] * 8000)  # 0.5s
        self.assertIsNone(hop)
        hop2, interim = sstt.feed([100] * 24000)  # total 2.0s
        self.assertEqual(hop2, "token1")
        self.assertEqual(interim, "token1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
