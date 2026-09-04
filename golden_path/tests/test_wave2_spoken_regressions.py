"""Wave 2 integration — FINAL spoken output regressions (no live LLM)."""
from __future__ import annotations

import unittest

from golden_path import GoldenPathEngine
from golden_path.llm import MockLLM
from golden_path.spoken_quality import check_spoken_quality


class Wave2SpokenRegressionTests(unittest.TestCase):
    """Control-flow turns must produce acceptable FINAL text without LLM."""

    def setUp(self) -> None:
        self.engine = GoldenPathEngine(llm=MockLLM(), session_id="wave2-spoken-test")
        self.engine.begin_session()

    def _turn(self, user: str) -> str:
        return self.engine.handle_turn(user).assistant_text

    def test_wave2_script_control_turns(self) -> None:
        self._turn("нормально")
        self._turn("настроение хорошее")
        self._turn("спал хорошо")
        why = self._turn("а зачем вы звоните?")
        correction = self._turn("нет, не голова, спина")
        fatigue = self._turn("я устал уже отвечать")
        close = self._turn("да ничего не планирую")

        for label, text in (
            ("WHY_CALLING", why),
            ("CORRECTION", correction),
            ("FATIGUE", fatigue),
            ("CLOSE", close),
        ):
            self.assertEqual(
                check_spoken_quality(text),
                [],
                msg=f"{label} FINAL failed quality: {text!r}",
            )

        self.assertNotIn("передать", why.lower())
        self.assertIn("чувствуете", why.lower())
        self.assertIn("берегите", close.lower())
        self.assertNotIn("попрощайтесь", close.lower())
        self.assertIn("спин", correction.lower())
        self.assertNotIn("?", correction)

    def test_wave2_control_before_close(self) -> None:
        self._turn("нормально")
        self._turn("настроение хорошее")
        self._turn("спал хорошо")
        refusal = self._turn("не хочу про настроение")
        wait = self._turn("секундочку")
        repair = self._turn("что вы спросили?")

        for label, text in (
            ("REFUSAL", refusal),
            ("WAIT", wait),
            ("REPAIR", repair),
        ):
            self.assertEqual(
                check_spoken_quality(text),
                [],
                msg=f"{label} FINAL failed quality: {text!r}",
            )

        self.assertIn("не будем", refusal.lower())
        self.assertIn("план", repair.lower())
        self.assertNotIn("что вас интересует", repair.lower())

    def test_close_blocks_further_turns(self) -> None:
        self._turn("нормально")
        self._turn("настроение хорошее")
        self._turn("спал хорошо")
        self._turn("да ничего не планирую")
        self.assertTrue(self.engine._ended)
        with self.assertRaises(RuntimeError):
            self._turn("не хочу про настроение")


if __name__ == "__main__":
    unittest.main()
