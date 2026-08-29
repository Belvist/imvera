"""U9 regression: STT confidence -> Observation -> safety verdict.

Covers the deterministic confidence computation (audio-energy gate + whisper
segment metrics), the STT adapter contract, StreamingSTT capture, the safety
engine's low-confidence guard on the control-question path, and the
orchestrator passing confidence into the Agent.
"""
import os
import struct
import sys
import tempfile
import unittest

os.environ.setdefault("MOSS_NO_WARMUP", "1")

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from adapters.stt import (  # noqa: E402
    STTResult,
    STTEngine,
    audio_energy,
    confidence_from_result,
    confidence_from_segments,
)
from core.events import StreamingSTT  # noqa: E402
from core.safety_engine import SafetyEngine, Observation  # noqa: E402


def _wav_bytes(amplitude=0, n=1600, rate=16000):
    body = struct.pack("<%dh" % n, *([amplitude] * n))
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(body)
    return buf.getvalue()


def _tmp_wav(amplitude=0):
    fd, p = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with open(p, "wb") as f:
        f.write(_wav_bytes(amplitude))
    return p


class _Seg:
    def __init__(self, **kw):
        self._kw = kw

    def get(self, k, d=None):
        return self._kw.get(k, d)


class AudioEnergyTests(unittest.TestCase):
    def test_silence_is_low(self):
        p = _tmp_wav(0)
        try:
            self.assertLess(audio_energy(p), 0.001)
        finally:
            os.remove(p)

    def test_speech_like_is_high(self):
        p = _tmp_wav(8000)
        try:
            self.assertGreater(audio_energy(p), 0.1)
        finally:
            os.remove(p)

    def test_unreadable_returns_full_energy(self):
        fd, p = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        with open(p, "w") as f:
            f.write("not a wav")
        try:
            self.assertEqual(audio_energy(p), 1.0)
        finally:
            os.remove(p)


class ConfidenceMappingTests(unittest.TestCase):
    def test_no_segments_returns_none(self):
        self.assertIsNone(confidence_from_segments([]))

    def test_high_no_speech_is_hallucination(self):
        segs = [_Seg(no_speech_prob=0.9, compression_ratio=1.0, avg_logprob=-0.3)]
        self.assertEqual(confidence_from_segments(segs), 0.05)

    def test_high_compression_is_hallucination(self):
        segs = [_Seg(no_speech_prob=0.0, compression_ratio=2.9, avg_logprob=-0.3)]
        self.assertEqual(confidence_from_segments(segs), 0.15)

    def test_avg_logprob_maps_monotone(self):
        good = [_Seg(no_speech_prob=0.0, compression_ratio=1.0, avg_logprob=-0.4)]
        bad = [_Seg(no_speech_prob=0.0, compression_ratio=1.0, avg_logprob=-1.8)]
        cg, cb = confidence_from_segments(good), confidence_from_segments(bad)
        self.assertGreater(cg, 0.95)
        self.assertEqual(cb, 0.05)
        self.assertGreater(cg, cb)

    def test_result_silence_pins_low_even_with_clean_segments(self):
        p = _tmp_wav(0)
        try:
            segs = [_Seg(no_speech_prob=0.0, compression_ratio=1.0,
                         avg_logprob=-0.2)]
            conf = confidence_from_result(p, _FakeResult(segs))
            self.assertEqual(conf, 0.05)  # silence -> hallucination, period
        finally:
            os.remove(p)

    def test_result_speech_uses_segments(self):
        p = _tmp_wav(8000)
        try:
            segs = [_Seg(no_speech_prob=0.0, compression_ratio=1.0,
                         avg_logprob=-0.5)]
            conf = confidence_from_result(p, _FakeResult(segs))
            self.assertGreater(conf, 0.7)
        finally:
            os.remove(p)


class _FakeResult:
    def __init__(self, segments, text=""):
        self.segments = segments
        self.text = text


class _FakeModel:
    def __init__(self, result=None, raises=False):
        self._result = result
        self._raises = raises

    def generate(self, *a, **kw):
        if self._raises:
            raise RuntimeError("boom")
        return self._result


class STTEngineTests(unittest.TestCase):
    def test_transcribe_with_confidence_cleans_and_reports(self):
        eng = STTEngine()
        eng._model = _FakeModel(
            _FakeResult([_Seg(no_speech_prob=0.0, compression_ratio=1.0,
                              avg_logprob=-0.5)], text=" всё хорошо "))
        p = _tmp_wav(8000)
        try:
            res = eng.transcribe_with_confidence(p)
            self.assertEqual(res.text, "всё хорошо")
            self.assertGreater(res.confidence, 0.7)
        finally:
            os.remove(p)

    def test_transcribe_with_confidence_junk_is_none(self):
        eng = STTEngine()
        eng._model = _FakeModel(_FakeResult([], text="а"))
        p = _tmp_wav(8000)
        try:
            res = eng.transcribe_with_confidence(p)
            self.assertIsNone(res.text)
        finally:
            os.remove(p)

    def test_transcribe_with_confidence_error_is_empty(self):
        eng = STTEngine()
        eng._model = _FakeModel(raises=True)
        p = _tmp_wav(8000)
        try:
            res = eng.transcribe_with_confidence(p)
            self.assertIsNone(res.text)
            self.assertIsNone(res.confidence)
        finally:
            os.remove(p)

    def test_transcribe_clean_keeps_public_contract(self):
        eng = STTEngine()
        eng._model = _FakeModel(
            _FakeResult([_Seg(no_speech_prob=0.0, compression_ratio=1.0,
                              avg_logprob=-0.5)], text=" всё хорошо "))
        p = _tmp_wav(8000)
        try:
            self.assertEqual(eng.transcribe_clean(p), "всё хорошо")
        finally:
            os.remove(p)


class _FakeSTT:
    def __init__(self, text, confidence):
        self._text = text
        self._conf = confidence

    def transcribe(self, path):
        return self._text

    def transcribe_with_confidence(self, path):
        return STTResult(self._text, self._conf)


class StreamingSTTConfidenceTests(unittest.TestCase):
    def test_finish_captures_confidence_from_tail_decode(self):
        eng = _FakeSTT("всё хорошо", 0.12)
        stt = StreamingSTT(eng, sample_rate=16000)
        stt.feed([0] * 16000)            # well under the 3 s hop window
        text = stt.finish()              # empty hops -> tail decode path
        self.assertEqual(text, "всё хорошо")
        self.assertEqual(stt.confidence, 0.12)


class SafetyLowConfMachineTests(unittest.TestCase):
    def test_low_conf_affirmative_never_confirms_red(self):
        eng = SafetyEngine()
        eng.observe(Observation(raw_text="плохо", confidence=0.9))
        ev = eng.observe(Observation(raw_text="да", confidence=0.1))
        self.assertEqual(ev.kind, "uncertain_red")

    def test_low_conf_denial_never_clears_to_green(self):
        eng = SafetyEngine()
        eng.observe(Observation(raw_text="плохо", confidence=0.9))
        ev = eng.observe(Observation(raw_text="нет", confidence=0.1))
        self.assertNotEqual(ev.kind, "ok")
        self.assertEqual(ev.kind, "uncertain_red")

    def test_full_confidence_flow_still_works(self):
        eng = SafetyEngine()
        eng.observe(Observation(raw_text="плохо", confidence=0.9))
        ev = eng.observe(Observation(raw_text="да", confidence=0.9))
        self.assertEqual(ev.kind, "confirmed_red")


class OrchestratorConfidenceTests(unittest.TestCase):
    def _serve_with(self, stt):
        from conftest_or_paths import SAMPLE_REF
        from core.orchestrator import Serve

        class _Args:
            refs = [SAMPLE_REF]
            tts_port_file = None
            tts_port = None
            inference_steps = 6
            no_style = False
            outdir = os.path.join(_HERE, "_tmp_conf_calls")
            tts_host = None

        args = _Args()
        serve = Serve(args)
        serve.stt = stt
        serve.tts = _FakeTTS()
        serve.llm.ready()
        return serve

    def test_process_turn_passes_confidence_to_agent(self):
        serve = self._serve_with(_FakeSTT("всё хорошо", 0.12))
        p = _tmp_wav(8000)
        try:
            cid = serve.new_call()
            r = serve.process_turn(p, call_id=cid)
            self.assertEqual(r["transcript"], "всё хорошо")
            self.assertEqual(serve.get_call(cid).agent._last_confidence, 0.12)
        finally:
            os.remove(p)

    def test_process_turn_falls_back_when_no_confidence_api(self):
        class _PlainSTT:
            def transcribe_clean(self, path):
                return "всё хорошо"

        serve = self._serve_with(_PlainSTT())
        p = _tmp_wav(8000)
        try:
            cid = serve.new_call()
            serve.process_turn(p, call_id=cid)
            self.assertIsNone(serve.get_call(cid).agent._last_confidence)
        finally:
            os.remove(p)


class _FakeTTS:
    def ready(self):
        return True

    def health(self):
        return True, None

    def generate(self, text):
        return _wav_bytes(8000)


class BlankTurnDiagTests(unittest.TestCase):
    """Regression: the phone-path "she can't hear me" attribution is cheap,
    deterministic and never throws (so a blank turn can't crash with it)."""

    def setUp(self):
        from core.orchestrator import Serve

        class _Args:
            refs = []
            tts_port_file = None
            tts_port = None
            inference_steps = 6
            no_style = False
            outdir = "/tmp/mossvoice_blank_diag"
            tts_host = None

        serve = Serve(_Args())
        serve.tts = _FakeTTS()
        serve.llm.ready()
        self.serve = serve
        # offline: stub Silero VAD (torch) and the audio-energy gate
        import sys
        import types

        fake_tts = types.ModuleType("tts_common")
        fake_tts.vad_speech_seconds = lambda _p, *_a, **_k: 0.05
        sys.modules["tts_common"] = fake_tts
        import adapters.stt as _stt
        self._real_energy = _stt.audio_energy
        _stt.audio_energy = lambda _p: 0.0015

    def tearDown(self):
        import adapters.stt as stt
        stt.audio_energy = self._real_energy
        import sys
        sys.modules.pop("tts_common", None)

    def _capture(self, *a, **k):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.serve._blank_turn_diag(*a, **k)
        return buf.getvalue()

    def test_silent_is_attributed(self):
        p = _tmp_wav(100)
        try:
            out = self._capture(p, "abc123", 0.05, None)
        finally:
            os.remove(p)
        self.assertIn("cause=SILENT", out)
        self.assertIn("abc123", out)

    def test_never_raises(self):
        # missing file -> audio_energy returns 1.0 (decode-hiccup fallback);
        # must still not throw.
        out = self._capture("/nonexistent/abc.wav", "x1", 0.05, None)
        self.assertIsInstance(out, str)

    def test_retainible_under_env(self):
        # FIX 2026-08-27: the assertion used a FIXED /tmp dir, so files left
        # by previous runs made len(hits)>1 flaky. Isolate per test.
        import os
        import tempfile
        tmp = tempfile.mkdtemp(prefix="moss_blank_diag_")
        self.serve.tmpdir = tmp
        os.environ["MOSS_RETAIN_BLANK_AUDIO"] = "1"
        try:
            p = _tmp_wav(200)
            try:
                self._capture(p, "ret1", 0.05, None)
            finally:
                os.remove(p)
            hits = [f for f in os.listdir(os.path.join(tmp, "blank_audio"))
                    if f.startswith("ret1_")]
            self.assertEqual(len(hits), 1)
        finally:
            os.environ.pop("MOSS_RETAIN_BLANK_AUDIO", None)
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)