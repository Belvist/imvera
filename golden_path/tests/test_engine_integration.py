"""Engine integration tests — MockLLM allowed here only."""
from __future__ import annotations

import unittest
from pathlib import Path

from golden_path.engine import GoldenPathEngine
from golden_path.llm import MockLLM
from golden_path.planner import PlannerAction
from golden_path.slots import SlotName, SlotStatus


class EngineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = GoldenPathEngine(llm=MockLLM(), session_id="int-test")

    def test_session_greeting(self) -> None:
        text = self.engine.begin_session()
        self.assertIn("Вера", text)
        self.assertTrue(self.engine.state.greeted)

    def test_safety_plan(self) -> None:
        self.engine.begin_session()
        result = self.engine.handle_turn("я упал")
        self.assertEqual(result.plan.action, PlannerAction.SAFETY)
        low = result.assistant_text.lower()
        self.assertNotIn("записала", low)
        self.assertNotIn("близкие увидят", low)
        self.assertIn("линии", low)

    def test_close_ends_session(self) -> None:
        self.engine.begin_session()
        self.engine.handle_turn("нормально")
        self.engine.handle_turn("настроение хорошее")
        self.engine.handle_turn("спал хорошо")
        close = self.engine.handle_turn("да ничего не планирую")
        self.assertEqual(close.plan.action, PlannerAction.CLOSE)
        self.assertIn("до свидания", close.assistant_text.lower())
        self.assertTrue(self.engine.state.closing)
        self.assertTrue(self.engine._ended)
        with self.assertRaises(RuntimeError):
            self.engine.handle_turn("не хочу про настроение")

    def test_user_question_answered_first(self) -> None:
        self.engine.begin_session()
        result = self.engine.handle_turn("а вы кто?")
        self.assertEqual(result.plan.action, PlannerAction.ANSWER_USER)

    def test_trace_file_exists(self) -> None:
        self.engine.begin_session()
        self.engine.handle_turn("нормально")
        self.assertTrue(Path(self.engine.trace_path).is_file())


if __name__ == "__main__":
    unittest.main()
