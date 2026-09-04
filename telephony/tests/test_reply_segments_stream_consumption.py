"""P0-A: reply_segments must consume full LLM stream (no early break)."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.events import reply_segments


class ReplySegmentsStreamConsumptionTests(unittest.TestCase):
    def test_consumes_at_least_three_deltas_and_closing_question(self):
        """Fake agent must yield all deltas; final text has closing question."""
        consumed: list[str] = []

        class _CountingAgent:
            def reply_stream(self, _plan):
                deltas = [
                    "Рада слышать, ",
                    "что вы в порядке. ",
                    "Как настроение сегодня?",
                ]
                for d in deltas:
                    consumed.append(d)
                    yield d

        plan = {"text": "хорошо", "allow_llm": True}
        segments = list(
            reply_segments(_CountingAgent(), plan, max_segments=4, max_chars=500)
        )
        combined = " ".join(segments)
        self.assertGreaterEqual(len(consumed), 3)
        self.assertIn("настроение", combined.lower())
        self.assertIn("?", combined)

    def test_early_comma_cut_does_not_stop_delta_loop(self):
        chunks = [
            "Понимаю, ",
            "это важно. ",
            "Как спали ночью?",
        ]
        consumed: list[str] = []

        class _Agent:
            def reply_stream(self, _plan):
                for c in chunks:
                    consumed.append(c)
                    yield c

        segs = list(
            reply_segments(_Agent(), {"allow_llm": True}, max_segments=4)
        )
        self.assertGreaterEqual(len(consumed), 3)
        combined = " ".join(segs)
        self.assertIn("спали", combined.lower())
        self.assertIn("?", combined)

    def test_drops_repeated_question_sentence(self):
        chunks = [
            "Понятно. Чем планируете заняться сегодня? ",
            "Чем планируете заняться сегодня?",
        ]
        consumed: list[str] = []

        class _Agent:
            def reply_stream(self, _plan):
                for c in chunks:
                    consumed.append(c)
                    yield c

        segs = list(
            reply_segments(_Agent(), {"allow_llm": True}, max_segments=4)
        )
        combined = " ".join(segs)
        self.assertEqual(combined.count("?"), 1)
        self.assertIn("планируете", combined.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
