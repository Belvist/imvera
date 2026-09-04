"""Unified STT gate tests."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.stt_gates import gate_stt_transcript  # noqa: E402
from core.vocab import repair_fall_miscue  # noqa: E402


class SttGatesTests(unittest.TestCase):
    def test_low_conf_blank(self):
        text, reason = gate_stt_transcript("тортичина", 0.40)
        self.assertEqual(text, "")
        self.assertEqual(reason, "low_conf")

    def test_short_wellness_survives_low_conf(self):
        text, reason = gate_stt_transcript("хорошо", 0.12)
        self.assertEqual(text, "хорошо")
        self.assertIsNone(reason)

        text, reason = gate_stt_transcript("плохо", 0.05)
        self.assertEqual(text, "плохо")
        self.assertIsNone(reason)

    def test_garbage_blank(self):
        text, reason = gate_stt_transcript("Торатичина", 0.90)
        self.assertEqual(text, "")
        self.assertEqual(reason, "low_conf")

    def test_mid_conf_confirm(self):
        text, reason = gate_stt_transcript("может быть", 0.65)
        self.assertEqual(text, "может быть")
        self.assertEqual(reason, "stt_uncertain")

    def test_clear_refusal_skips_confirm(self):
        text, reason = gate_stt_transcript("Ничего не нужно.", 0.78)
        self.assertEqual(text, "Ничего не нужно.")
        self.assertIsNone(reason)

    def test_mood_phrase_skips_uncertain_confirm(self):
        text, reason = gate_stt_transcript("Хорошее настроение.", 0.65)
        self.assertEqual(text, "Хорошее настроение.")
        self.assertIsNone(reason)

    def test_high_conf_passes(self):
        text, reason = gate_stt_transcript("да всё хорошо", 0.90)
        self.assertEqual(text, "да всё хорошо")
        self.assertIsNone(reason)

    def test_fall_miscue_repaired(self):
        raw = "у палок не ударилось"
        text, reason = gate_stt_transcript(raw, 0.90)
        self.assertIn("упал", text)
        self.assertIsNone(reason)

    def test_repair_fall_miscue_unit(self):
        self.assertIn("упал", repair_fall_miscue("у палок не ударилось"))
        self.assertEqual(repair_fall_miscue("я упала"), "я упала")

    def test_high_conf_caller_controls_survive_vocab_gate(self):
        for raw in (
            "а кто вы такая",
            "вы записываете разговор",
            "я не понял вопрос",
            "я не могу встать",
        ):
            with self.subTest(raw=raw):
                text, reason = gate_stt_transcript(raw, 0.90)
                self.assertEqual(text, raw)
                self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
