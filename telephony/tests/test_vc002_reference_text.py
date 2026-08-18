"""P0-VC-002 / P0-VC-004 regression:

* when a client supplies reference_text it is used verbatim (source=="client"),
* with no reference_text the daemon falls back to STT on the *merged* (and
  possibly 15 s-truncated) audio so the transcript matches what the model hears,
* alignment: transcript is derived from the truncated merged clip, not from a
  longer source clip.
"""
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from conftest_or_paths import RUNTIME_SCRIPTS, SAMPLE_REF  # noqa: E402

sys.path.insert(0, RUNTIME_SCRIPTS)

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
import tts_common  # noqa: E402
from tts_server import TTSWorker  # noqa: E402


class _FakeSTT:
    """Records what audio it was asked to transcribe; returns canned text."""

    def __init__(self, text):
        self.text = text
        self.seen = []

    def generate(self, path, verbose=False, task="transcribe", language=None):
        self.seen.append((path, language))
        return type("R", (), {"text": self.text})()


class _FakeTTSModel:
    _is_qwen3 = True

    def __init__(self, is_qwen):
        self._is_qwen3 = is_qwen

    def build_prompt_cache(self, reference_wav_path=None, ref_text=None):
        return f"prompt:{reference_wav_path}:{ref_text}"


class _FakeTTS:
    def __init__(self, is_qwen):
        self.tts_model = _FakeTTSModel(is_qwen)


def _bare_worker(stt_text="какой?то текст", is_qwen=True, use_model=False):
    import threading as _t

    w = TTSWorker.__new__(TTSWorker)
    w.model_id = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit"
    w._tts = _FakeTTS(is_qwen) if use_model else None
    w._stt_model_id = None
    w.stt_model = _FakeSTT(stt_text)
    w.stt_model_loaded = True
    w.merged_refs = {}
    w.prompt_cache = {}
    w.transcripts = {}
    w.ref_meta = {}
    w._lock = _t.Lock()
    w._merged_lk = _t.Lock()
    return w


def _make_wav(path, seconds, sr=16000):
    x = (0.5 * np.sin(2 * np.pi * 220 * np.arange(int(sr * seconds)) / sr)).astype(np.float32)
    sf.write(path, x, sr)
    return path


class ReferenceTextResolutionTests(unittest.TestCase):
    def test_client_text_wins(self):
        w = _bare_worker(stt_text="а-авто")
        _, merged = w._ensure_ref([SAMPLE_REF])
        text, source, secs = w._resolve_ref_text(merged, "клиентский текст")
        self.assertEqual(text, "клиентский текст")
        self.assertEqual(source, "client")
        self.assertIsNotNone(secs)

    def test_no_client_text_uses_stt(self):
        w = _bare_worker(stt_text="а-авто", use_model=True)
        _, merged = w._ensure_ref([SAMPLE_REF])
        text, source, secs = w._resolve_ref_text(merged, None)
        self.assertEqual(text, "а-авто")
        self.assertEqual(source, "stt")
        self.assertGreater(secs, 0)

    def test_stt_language_ru(self):
        w = _bare_worker(stt_text="тест", use_model=True)
        _, merged = w._ensure_ref([SAMPLE_REF])
        w._resolve_ref_text(merged, None)
        self.assertEqual(w.stt_model.seen[0][1], tts_common.STT_LANGUAGE)

    def test_none_when_no_merged(self):
        w = _bare_worker()
        text, source, secs = w._resolve_ref_text(None, "client text must pass")
        self.assertEqual(source, "client")

    def test_client_text_source_reported_in_cached_meta(self):
        w = _bare_worker(stt_text="а-авто", use_model=True)
        key, _cache = w._ensure_cache([SAMPLE_REF], "клиент")
        meta = w.ref_meta.get(key)
        self.assertEqual(meta["source"], "client")
        self.assertEqual(meta["text"], "клиент")


class AlignmentAfterTrimTests(unittest.TestCase):
    def test_transcript_matches_truncated_audio(self):
        """A 30 s clip is merged to <=REFERENCE_MAX_SECONDS; the fallback STT
        must see the truncated merged audio (not the 30 s original)."""
        src = tempfile.mkstemp(suffix=".wav")[1]
        _make_wav(src, 30.0)
        merged = tts_common.merge_references([src])
        self.assertIsNotNone(merged)
        secs = tts_common.audio_seconds(merged)
        self.assertLessEqual(secs, tts_common.REFERENCE_MAX_SECONDS + 0.2)

        # transcribe_merged() is fed the merged (truncated) file
        fake = _FakeSTT("после обрезки")
        text, secs2 = tts_common.transcribe_merged(merged, fake)
        self.assertEqual(text, "после обрезки")
        self.assertEqual(fake.seen[0][0], merged)
        self.assertLessEqual(secs2, tts_common.REFERENCE_MAX_SECONDS + 0.2)

        w = _bare_worker(stt_text="после обрезки", use_model=True)
        text2, source, secs3 = w._resolve_ref_text(merged, None)
        self.assertEqual(source, "stt")
        self.assertLessEqual(secs3, tts_common.REFERENCE_MAX_SECONDS + 0.2)
        try:
            os.remove(merged)
        except OSError:
            pass
        try:
            os.remove(src)
        except OSError:
            pass


if __name__ == "__main__":
    unittest.main(verbosity=2)