"""Pronunciation + speech frontend tests (offline, no torch)."""
from __future__ import annotations

import os
import sys
import unittest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_RUNTIME = os.path.join(_REPO, "runtime", "scripts")
_MOSS_RT = os.path.join(_RUNTIME, "moss_runtime")
for _p in (_MOSS_RT,):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pronunciation import apply_pronunciation, apply_pronunciation_with_trace  # noqa: E402
from speech_frontend import build_tts_trace, normalize_text, to_ssml  # noqa: E402


class PronunciationTests(unittest.TestCase):
    def test_imvera_brand_stress(self) -> None:
        out = apply_pronunciation("Это Вера из Имвера.")
        self.assertIn("+Имвера", out)
        self.assertIn("В+ера", out)

    def test_latin_imvera_replaced(self) -> None:
        out = apply_pronunciation("Welcome to IMVERA")
        self.assertIn("+Имвера", out)
        self.assertNotIn("IMVERA", out)

    def test_homograph_zvonit(self) -> None:
        out = apply_pronunciation("Он позвонит вам завтра.")
        self.assertIn("позвон+ит", out)

    def test_clinic_vocabulary(self) -> None:
        out = apply_pronunciation("Регистратура на первом этаже поликлиники.")
        self.assertIn("регистрат+ура", out)
        self.assertIn("поликлин+ики", out)

    def test_ssml_path_preserves_stress_marks(self) -> None:
        prepared = apply_pronunciation("Здравствуйте! Это Вера из Имвера.")
        ssml = to_ssml(prepared)
        self.assertIsNotNone(ssml)
        assert ssml is not None
        self.assertIn("+Имвера", ssml)
        self.assertIn("<break", ssml)

    def test_normalize_dates_after_pronunciation(self) -> None:
        out = normalize_text(apply_pronunciation("Звонок 21.08 в 18:30."))
        self.assertIn("августа", out)
        self.assertIn("восемнадцать", out)

    def test_pronunciation_trace_records_overrides(self) -> None:
        trace = apply_pronunciation_with_trace("Имвера позвонит вам вечером.")
        self.assertIn("+Имвера", trace.normalized)
        self.assertIn("позвон+ит", trace.normalized)
        kinds = {o.kind for o in trace.overrides}
        self.assertIn("word", kinds)
        self.assertTrue(trace.format_lines().startswith("TTS_INPUT_ORIGINAL:"))

    def test_build_tts_trace_includes_ssml(self) -> None:
        trace = build_tts_trace("Это Вера из Имвера. Как дела?")
        self.assertIn("+Имвера", trace["TTS_INPUT_NORMALIZED"])
        self.assertIsNotNone(trace.get("TTS_SSML"))


if __name__ == "__main__":
    unittest.main()
