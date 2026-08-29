"""Vocab gate (FIXES_PLAN P1b, 2026-08-29): confident-looking whisper
nonsense must not reach the dialogue/LLM. Real speech and critical health
entities (fall/pain/meds/doctor) must never be gated away."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.vocab import (  # noqa: E402
    looks_like_garbage, contains_real_word)


class VocabGateTests(unittest.TestCase):
    def test_real_speech_never_garbage(self):
        real = [
            "Алло, да, слышно меня",
            "Да, да, да, я тебя слышу",
            "привет, хорошо чувствую себя",
            "хорошая настроение",
            "настроение хорошее, спасибо",
            "спала хорошо",
            "внучка приезжала, мы чай пили",
            "приняла таблетку от давления",
            "буду читать книгу",
            "посмотрела телевизор",
            "гуляла на улице",
            "пока",
            "пожалуйста",
            "здравствуйте",
            "не знаю",
            "да нормально все",
            "хочу отдохнуть",
            "сон хороший был",
            "всё хорошо",
            "плохо",
        ]
        for t in real:
            self.assertFalse(looks_like_garbage(t), f"real speech gated: {t!r}")

    def test_observed_nonsense_is_garbage(self):
        noise = [
            "Торатичина",
            "Лоха!",
            "Сам оттвыж",
            "Варите осуши",
            "восподнанговаривании",
        ]
        for t in noise:
            self.assertTrue(looks_like_garbage(t), f"noise passed gate: {t!r}")

    def test_critical_health_entity_never_gated(self):
        # "у палок не ударилось" is the real fall-miscue from ca81bc3ac2c7:
        # «удар» keeps the turn so the fall is not silently lost.
        for t in ("у палок не ударилось", "я упала", "голова болит",
                  "давление упало", "принимаю лекарство", "вызовите врача",
                  "сердце болит", "температура высокая"):
            self.assertFalse(looks_like_garbage(t),
                             f"critical entity gated: {t!r}")
            self.assertTrue(contains_real_word(t), t)

    def test_empty_not_classified(self):
        self.assertFalse(looks_like_garbage(""))
        self.assertFalse(looks_like_garbage(None))
        self.assertFalse(looks_like_garbage("   "))


if __name__ == "__main__":
    unittest.main(verbosity=2)