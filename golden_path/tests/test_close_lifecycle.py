"""CLOSE must end session — no turns after goodbye."""
from __future__ import annotations

import unittest

from golden_path.engine import GoldenPathEngine
from golden_path.llm import MockLLM
from golden_path.planner import PlannerAction


class CloseLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = GoldenPathEngine(llm=MockLLM(), session_id="close-lifecycle")

    def test_all_slots_closed_ends_session(self) -> None:
        self.engine.begin_session()
        self.engine.handle_turn("нормально")
        self.engine.handle_turn("настроение хорошее")
        self.engine.handle_turn("спал хорошо")
        result = self.engine.handle_turn("да ничего не планирую")
        self.assertEqual(result.plan.action, PlannerAction.CLOSE)
        self.assertTrue(self.engine._ended)
        with self.assertRaises(RuntimeError):
            self.engine.handle_turn("секундочку")

    def test_goodbye_close_also_ends_session(self) -> None:
        self.engine.begin_session()
        result = self.engine.handle_turn("до свидания")
        self.assertEqual(result.plan.action, PlannerAction.CLOSE)
        self.assertTrue(self.engine._ended)
        with self.assertRaises(RuntimeError):
            self.engine.handle_turn("пока")


if __name__ == "__main__":
    unittest.main()
