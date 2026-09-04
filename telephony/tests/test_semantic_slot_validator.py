"""P0-F: semantic slot validator rejects wrong-slot output before TTS."""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation_system.reply.spoken import resolve_spoken_reply


class _Mirror:
    llm_history: list = []
    _last_reply: str = ""


class SemanticSlotValidatorTests(unittest.TestCase):
    def test_sleep_slot_rejects_mood_question(self):
        plan = {
            "allow_llm": True,
            "fallback": "Как спали ночью?",
            "current_slot": "сон",
            "agenda_context": {"current_slot": "сон"},
            "text": "хорошо",
        }
        wrong = "Рада слышать. Как настроение сегодня?"
        spoken = resolve_spoken_reply(_Mirror(), plan, wrong)
        self.assertIn("спал", spoken.lower())
        self.assertNotIn("настроение", spoken.lower())

    def test_mood_slot_rejects_sleep_question(self):
        plan = {
            "allow_llm": True,
            "fallback": "Как настроение?",
            "current_slot": "настроение",
            "agenda_context": {"current_slot": "настроение"},
            "text": "хорошо",
        }
        wrong = "Понятно. Как спали ночью?"
        spoken = resolve_spoken_reply(_Mirror(), plan, wrong)
        self.assertIn("настроен", spoken.lower())
        self.assertNotIn("спал", spoken.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
