"""Content plan unit tests."""
from __future__ import annotations

import unittest

from golden_path.analyzer import Analysis, AnalysisKind, AnswerType
from golden_path.content_plan import build_content_plan
from golden_path.planner import Plan, PlannerAction
from golden_path.slots import SlotName, SlotStatus
from golden_path.state import ConversationState


class ContentPlanTests(unittest.TestCase):
    def test_ask_sleep_plan(self) -> None:
        state = ConversationState()
        state.greeted = True
        state.slot_statuses[SlotName.WELLNESS] = SlotStatus.ANSWERED
        state.slot_statuses[SlotName.MOOD] = SlotStatus.ANSWERED
        plan = Plan(PlannerAction.ASK_SLOT, slot=SlotName.SLEEP)
        analysis = Analysis(
            kind=AnalysisKind.NORMAL_RESPONSE,
            facts={"answered_slot": SlotName.MOOD.value},
        )
        cp = build_content_plan(plan, state, analysis, "настроение хорошее")
        self.assertEqual(cp.action, "ASK_SLOT(sleep)")
        self.assertEqual(cp.required_question, "sleep_last_night")
        self.assertIn("настроение", cp.forbidden_topics)
        self.assertTrue(any("сон" in b for b in cp.semantic_bullets))

    def test_correction_plan(self) -> None:
        state = ConversationState()
        state.facts["symptom"] = "back"
        plan = Plan(PlannerAction.HANDLE_CORRECTION)
        analysis = Analysis(
            kind=AnalysisKind.CORRECTION,
            facts={"symptom": "back"},
        )
        cp = build_content_plan(plan, state, analysis, "нет, не голова, спина")
        self.assertTrue(any("спин" in b for b in cp.semantic_bullets))
        self.assertTrue(any("спин" in f for f in cp.facts_to_reference))

    def test_why_calling_plan(self) -> None:
        state = ConversationState()
        state.pending_slot = SlotName.SLEEP
        plan = Plan(
            PlannerAction.ANSWER_USER,
            answer_type=AnswerType.WHY_CALLING,
        )
        analysis = Analysis(kind=AnalysisKind.DIRECT_USER_QUESTION)
        cp = build_content_plan(plan, state, analysis, "зачем вы звоните?")
        self.assertEqual(cp.action, "ANSWER_USER(WHY_CALLING)")
        self.assertIn("самочувствие", cp.forbidden_topics)


if __name__ == "__main__":
    unittest.main()
