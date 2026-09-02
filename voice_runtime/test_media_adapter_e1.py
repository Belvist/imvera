"""Unit tests for E1 MediaAdapter helpers (PreRoll, GenerationGuard, Streaming)."""
from __future__ import annotations

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from media_adapter import (  # noqa: E402
    GenerationGuard,
    NullMedia,
    PreRollBuffer,
    StreamingPcmAdapter,
)


class PreRollTests(unittest.TestCase):
    def test_keeps_tail(self):
        buf = PreRollBuffer(ms=100, sample_rate=1000)  # 100 samples
        buf.push(list(range(250)))
        snap = buf.snapshot()
        self.assertEqual(len(snap), 100)
        self.assertEqual(snap[0], 150)

    def test_flush_clears(self):
        buf = PreRollBuffer(ms=300, sample_rate=16000)
        buf.push([7, 8, 9])
        out = buf.flush()
        self.assertEqual(out, [7, 8, 9])
        self.assertEqual(len(buf), 0)


class GenerationTests(unittest.TestCase):
    def test_bump_invalidates(self):
        g = GenerationGuard()
        gid = g.current()
        self.assertEqual(g.generation_id, gid)
        self.assertTrue(g.is_current(gid))
        new = g.bump()
        self.assertFalse(g.is_current(gid))
        self.assertTrue(g.is_current(new))
        self.assertEqual(g.generation_id, new)


class StreamingAdapterTests(unittest.TestCase):
    def test_push_and_drain(self):
        a = StreamingPcmAdapter(sample_rate=16000)
        a.push_frames([1, 2, 3, 4])
        frames = a.frames_in()
        self.assertEqual(frames, [1, 2, 3, 4])
        self.assertEqual(a.frames_in(), [])
        self.assertEqual(a.audio_bytes(), 8)

    def test_push_bytes(self):
        a = StreamingPcmAdapter()
        a.push_frames(struct.pack("<3h", 10, 20, 30))
        self.assertEqual(a.frames_in(), [10, 20, 30])

    def test_barge_in_generation(self):
        a = StreamingPcmAdapter()
        play_gid = a.generation.current()
        flushed = a.generation.bump()
        self.assertFalse(a.generation.is_current(play_gid))
        self.assertEqual(flushed, a.generation.current())

    def test_null_media(self):
        n = NullMedia()
        self.assertEqual(n.frames_in(), [])
        self.assertFalse(n.broken)


if __name__ == "__main__":
    unittest.main(verbosity=2)
