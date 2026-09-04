"""State reducer ordering — user turn applied before planner."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from golden_path.analyzer import analyze_turn
from golden_path.engine import GoldenPathEngine
from golden_path.llm import MockLLM
from golden_path.planner import PlannerAction, plan_turn
from golden_path.slots import SlotName, SlotStatus
from golden_path.state import ConversationState


class StateOrderingTests(unittest.TestCase):
    def _reduce_and_plan(self, state: ConversationState, user_text: str):
        analysis = analyze_turn(user_text, state)
        state.reduce_user_turn(
            user_text,
            analysis.kind.value,
            analysis.facts,
            refusal_slot=analysis.refusal_slot,
        )
        plan = plan_turn(state, analysis)
        return analysis, plan

    def test_normally_marks_wellness_before_planner(self) -> None:
        state = ConversationState()
        state.greeted = True
        state.pending_slot = SlotName.WELLNESS
        _, plan = self._reduce_and_plan(state, "нормально")
        self.assertEqual(state.slot_statuses[SlotName.WELLNESS], SlotStatus.ANSWERED)
        if plan.action == PlannerAction.ASK_SLOT:
            self.assertNotEqual(plan.slot, SlotName.WELLNESS)

    def test_mood_answered_before_planner(self) -> None:
        state = ConversationState()
        state.greeted = True
        state.slot_statuses[SlotName.WELLNESS] = SlotStatus.ANSWERED
        state.pending_slot = SlotName.MOOD
        _, plan = self._reduce_and_plan(state, "настроение хорошее")
        self.assertEqual(state.slot_statuses[SlotName.MOOD], SlotStatus.ANSWERED)
        if plan.action == PlannerAction.ASK_SLOT:
            self.assertNotEqual(plan.slot, SlotName.MOOD)

    def test_safety_flag_before_planner(self) -> None:
        state = ConversationState()
        state.greeted = True
        analysis, plan = self._reduce_and_plan(state, "мне трудно дышать")
        self.assertTrue(state.safety_active)
        self.assertEqual(plan.action, PlannerAction.SAFETY)

    def test_repair_flag_before_planner(self) -> None:
        state = ConversationState()
        state.greeted = True
        analysis, plan = self._reduce_and_plan(state, "что вы сказали?")
        self.assertTrue(state.repair_pending)
        self.assertEqual(plan.action, PlannerAction.REPAIR)

    def test_wait_request_flag_before_planner(self) -> None:
        state = ConversationState()
        state.greeted = True
        self._reduce_and_plan(state, "секундочку, я вспомню")
        self.assertTrue(state.wait_request)

    def test_user_fatigue_flag_before_planner(self) -> None:
        state = ConversationState()
        state.greeted = True
        self._reduce_and_plan(state, "я устал уже отвечать")
        self.assertTrue(state.user_fatigue)

    def test_correction_symptom_applied_once(self) -> None:
        state = ConversationState()
        analysis = analyze_turn("нет, не голова, спина", state)
        state.reduce_user_turn(
            "нет, не голова, спина",
            analysis.kind.value,
            analysis.facts,
        )
        self.assertEqual(state.facts.get("symptom"), "back")
        self.assertEqual(len(state.corrections), 1)

    def test_trace_contains_state_after_user(self) -> None:
        engine = GoldenPathEngine(llm=MockLLM(), session_id="ordering-trace")
        engine.begin_session()
        engine.handle_turn("нормально")
        trace_path = Path(engine.trace_path)
        lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
        turn_line = next(line for line in lines if '"turn_no": 1' in line)
        record = json.loads(turn_line)
        self.assertIn("state_after_user", record)
        self.assertEqual(
            record["state_after_user"]["slot_statuses"]["wellness"],
            SlotStatus.ANSWERED.value,
        )


if __name__ == "__main__":
    unittest.main()
