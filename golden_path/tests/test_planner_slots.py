"""Planner + slot immutability tests."""
from __future__ import annotations

import unittest

from golden_path.analyzer import Analysis, AnalysisKind
from golden_path.planner import PlannerAction, plan_turn
from golden_path.slots import SlotName, SlotStatus
from golden_path.state import ConversationState


class PlannerSlotTests(unittest.TestCase):
    def test_mood_answered_not_reasked(self) -> None:
        state = ConversationState()
        state.greeted = True
        state.slot_statuses[SlotName.WELLNESS] = SlotStatus.ANSWERED
        state.slot_statuses[SlotName.MOOD] = SlotStatus.ANSWERED
        state.slot_statuses[SlotName.SLEEP] = SlotStatus.OPEN
        state.turns_since_question = 2

        plan = plan_turn(state, Analysis(kind=AnalysisKind.NORMAL_RESPONSE))
        if plan.action == PlannerAction.ASK_SLOT:
            self.assertNotEqual(plan.slot, SlotName.MOOD)
            self.assertNotEqual(plan.slot, SlotName.WELLNESS)

    def test_declined_slot_skipped(self) -> None:
        state = ConversationState()
        state.greeted = True
        state.slot_statuses[SlotName.MOOD] = SlotStatus.DECLINED
        state.slot_statuses[SlotName.WELLNESS] = SlotStatus.ANSWERED
        state.turns_since_question = 2

        plan = plan_turn(state, Analysis(kind=AnalysisKind.NORMAL_RESPONSE))
        if plan.action == PlannerAction.ASK_SLOT:
            self.assertNotEqual(plan.slot, SlotName.MOOD)

    def test_user_question_gets_answer_user(self) -> None:
        state = ConversationState()
        state.greeted = True
        state.turns_since_question = 2
        analysis = Analysis(kind=AnalysisKind.DIRECT_USER_QUESTION, user_question="кто вы?")
        plan = plan_turn(state, analysis)
        self.assertEqual(plan.action, PlannerAction.ANSWER_USER)


if __name__ == "__main__":
    unittest.main()
