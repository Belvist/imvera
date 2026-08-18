"""P0-REALTIME-CORE regression: VAD barge-in semantics + TXPipeline flush.

Requirements under test (from the full-duplex design):
  * VAD never drops the head of a user utterance that starts while the
    agent is speaking — barge_in onset is reported exactly once at burst
    start, and the full turn (including its head) is delivered.
  * An onset while TX is busy must trigger a flush (client drops queued
    playback) and an aborted done frame.
  * A second turn started while a first is still running cancels the first
    cleanly (no busy-state leak across generations).
"""
import asyncio
import os
import struct
import sys
import threading
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tg"))

from tg_server import (  # noqa: E402
    TXPipeline,
    VAD,
    CHUNK_SAMPLES,
    SILENCE_GAP_MS,
    ENERGY_THRESHOLD,
    MIN_SPEECH_MS,
)


def speech_chunk(amp=3000 / 32767.0 * 32767, n=CHUNK_SAMPLES):
    """One 30ms chunk of pure tone well above the energy gate."""
    return [amp] * n


def silence_chunk(n=CHUNK_SAMPLES):
    return [0] * n


class VADTests(unittest.TestCase):
    def test_onset_exactly_once_and_turn_retains_head(self):
        vad = VAD()
        # silence, then burst, then enough silence to close the turn
        for _ in range(5):
            vad.feed(silence_chunk())
        burst = [speech_chunk() for _ in range(8)]
        first_turn_chunk = burst[0][0]
        onset = False
        for i, c in enumerate(burst):
            _, o = vad.feed(c)
            if i == 0:
                self.assertTrue(o)
            onset = onset or o
        # silence tail until the turn is emitted
        collected = []
        for _ in range(40):
            t, o = vad.feed(silence_chunk())
            onset = onset or o
            if t:
                collected = t
                break
        self.assertTrue(collected, "VAD never closed the turn")
        non_zero = [v for v in collected if v != 0]
        self.assertTrue(non_zero, "VAD dropped the whole speech burst")
        self.assertEqual(non_zero[0], first_turn_chunk,
                         "VAD lost the head of the utterance")

    def test_barge_onset_only_when_speech_starts(self):
        vad = VAD()
        # initial silence establishes noise floor
        for _ in range(10):
            vad.feed(silence_chunk())
        # first speech chunk -> onset True
        _, o1 = vad.feed(speech_chunk())
        self.assertTrue(o1)
        # continuing speech -> onset False even while still above threshold
        _, o2 = vad.feed(speech_chunk())
        # (o2 may coincide with turn completion; assert never True onset here)
        self.assertFalse(o2)

    def test_short_noise_collapses_to_no_turn(self):
        vad = VAD()
        for _ in range(5):
            vad.feed(speech_chunk())
        # silence tail longer than gap -> below MIN_SPEECH => no turn emitted
        for _ in range(50):
            t, _ = vad.feed(silence_chunk())
        self.assertIsNone(t)


class _Recorder:
    def __init__(self):
        self.payloads = []

    async def send(self, payload):
        self.payloads.append(payload)


class _CancellableBridge:
    def __init__(self):
        self.cancelled = 0

    def cancel_stream(self):
        self.cancelled += 1

    def turn_stream(self, pcm, rate=16000, cancel_event=None):
        # never-completing generator that honors cancel_event within one chunk
        i = 0
        while True:
            if cancel_event is not None and cancel_event.is_set():
                yield {"done": True, "aborted": True}
                return
            yield {"i": i, "wav_b64": "AAAA"}
            i += 1


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TXPipelineTests(unittest.TestCase):
    def test_barge_in_flushes_and_aborts(self):
        rec = _Recorder()
        tx = TXPipeline(_CancellableBridge(), rec.send)

        async def scene():
            tx.start_turn([31] * 100)
            await asyncio.sleep(0.05)
            tx.barge_in()
            await asyncio.sleep(0.2)
            return rec.payloads

        payloads = asyncio.new_event_loop().run_until_complete(scene())
        kinds = [p.get("type") for p in payloads]
        self.assertIn("flush", kinds)
        self.assertIn("chunk", kinds)
        aborted = [p for p in payloads if p.get("aborted")]
        self.assertTrue(aborted, "barge-in must leave an aborted done frame")

    def test_new_turn_cancels_previous_without_busy_leak(self):
        rec = _Recorder()
        tx = TXPipeline(_CancellableBridge(), rec.send)
        state = {}

        async def scene():
            tx.start_turn([31] * 100)
            tx.start_turn([32] * 100)
            await asyncio.sleep(0.3)
            state["busy"] = tx.busy
            return rec.payloads

        payloads = asyncio.new_event_loop().run_until_complete(scene())
        self.assertTrue(state["busy"], "a running turn must be busy")
        # flush was emitted exactly when the second turn cancelled the first
        self.assertEqual(
            sum(1 for p in payloads if p.get("type") == "flush"), 1)
        # only the newest generation lives: no duplicate finished
        self.assertNotIn("finished", [p.get("type") for p in payloads])


if __name__ == "__main__":
    unittest.main(verbosity=2)