"""Unit tests for streaming ingress proof (Wave RT-1)."""
from __future__ import annotations

import os
import struct
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from ingress_session import GatewayIngressSession
from ingress_trace import IngressTrace
from text_chunker import StreamTextChunker
from turn_detector import TunedEndpointPolicy
from vad import SAMPLE_RATE
from voice_gateway.server import VoiceGatewayServer


def _pack(samples: list[int]) -> bytes:
    return struct.pack("<" + "h" * len(samples), *samples)


def _loud_chunk(n: int | None = None) -> list[int]:
    count = n or int(SAMPLE_RATE * 0.03)
    return [5000] * count


def _quiet_chunk(n: int | None = None) -> list[int]:
    count = n or int(SAMPLE_RATE * 0.03)
    return [0] * count


class IngressTraceTests(unittest.TestCase):
    def test_prove_requires_frames_during_speech(self):
        tr = IngressTrace(call_id="t1")
        tr.mark("pcm_frame", sequence=1, nbytes=960, rms=100.0, speech_active=True)
        tr.speech_start()
        tr.mark("pcm_frame", sequence=2, nbytes=960, rms=5000.0, speech_active=True)
        tr.mark("pcm_frame", sequence=3, nbytes=960, rms=5000.0, speech_active=True)
        tr.speech_end()
        proof = tr.prove_continuous_ingress()
        self.assertTrue(proof["ok"])
        self.assertGreaterEqual(proof["frames_during_speech"], 3)


class TurnDetectorTests(unittest.TestCase):
    def test_short_speech_not_complete(self):
        td = TunedEndpointPolicy(min_speech_ms=220, endpoint_silence_ms=700)
        d = td.is_complete(
            speech_active=False,
            silence_ms=800,
            speech_ms=100,
            vad_turn_ready=True,
        )
        self.assertFalse(d.complete)

    def test_sufficient_silence_completes(self):
        td = TunedEndpointPolicy(min_speech_ms=200, endpoint_silence_ms=500)
        d = td.is_complete(
            speech_active=False,
            silence_ms=600,
            speech_ms=400,
            vad_turn_ready=True,
        )
        self.assertTrue(d.complete)
        self.assertEqual(d.source, "tuned_endpoint")


class IngressSessionTests(unittest.TestCase):
    def test_continuous_pcm_before_turn_commit(self):
        session = GatewayIngressSession(
            call_id="unit",
            turn_detector=TunedEndpointPolicy(
                min_speech_ms=200,
                endpoint_silence_ms=500,
            ),
        )
        for _ in range(10):
            session.feed_pcm(_pack(_loud_chunk()))
        for _ in range(20):
            session.feed_pcm(_pack(_quiet_chunk()))

        status = session.prove_status()
        self.assertEqual(status["status"], "STREAMING_INGRESS_PROVEN")
        proof = status["proof"]
        self.assertTrue(proof["ok"])
        self.assertIsNotNone(proof["last_pcm_before_end_ms"])


class TextChunkerTests(unittest.TestCase):
    def test_first_chunk_on_comma_boundary(self):
        c = StreamTextChunker()
        chunks = c.feed("Поняла, настроение сегодня хорошее. Как вы спали?")
        self.assertGreaterEqual(len(chunks), 1)
        self.assertIn(",", chunks[0])

    def test_waits_for_boundary_before_emit(self):
        c = StreamTextChunker(first_chunk_min_chars=20, first_chunk_max_chars=30)
        chunks = c.feed("Поняла настроение")
        self.assertEqual(chunks, [])
        chunks = c.feed(" сегодня хорошее.")
        self.assertGreaterEqual(len(chunks), 1)


class VoiceGatewayOfflineTests(unittest.TestCase):
    def test_server_feed_pcm_offline(self):
        gw = VoiceGatewayServer()
        turns: list[dict] = []
        gw.on_turn = turns.append
        for _ in range(8):
            gw.feed_pcm_offline("c1", _pack(_loud_chunk()))
        for _ in range(24):
            gw.feed_pcm_offline("c1", _pack(_quiet_chunk()))
        self.assertTrue(turns)
        self.assertTrue(turns[-1]["proof"]["ok"])


if __name__ == "__main__":
    unittest.main()
