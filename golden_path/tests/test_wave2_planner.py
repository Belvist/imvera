"""Wave 2 planner regression tests — P0-1 through P0-12."""
from __future__ import annotations

import unittest

from golden_path.analyzer import Analysis, AnalysisKind, AnswerType, analyze_turn
from golden_path.planner import PlannerAction, plan_turn
from golden_path.safety import SafetyPhase
from golden_path.slots import SlotName, SlotStatus
from golden_path.state import ConversationState


def _greeted_state(**kwargs: object) -> ConversationState:
    state = ConversationState()
    state.greeted = True
    for key, value in kwargs.items():
        setattr(state, key, value)
    return state


class Wave2GoodPathTests(unittest.TestCase):
    def test_wellness_answer_advances_to_mood_without_budget(self) -> None:
        state = _greeted_state()
        state.slot_statuses[SlotName.WELLNESS] = SlotStatus.ANSWERED
        state.turns_since_question = 0

        plan = plan_turn(
            state,
            Analysis(
                kind=AnalysisKind.NORMAL_RESPONSE,
                facts={"answered_slot": SlotName.WELLNESS.value},
            ),
        )
        self.assertEqual(plan.action, PlannerAction.ASK_SLOT)
        self.assertEqual(plan.slot, SlotName.MOOD)

    def test_mood_answer_advances_to_sleep(self) -> None:
        state = _greeted_state()
        state.slot_statuses[SlotName.WELLNESS] = SlotStatus.ANSWERED
        state.slot_statuses[SlotName.MOOD] = SlotStatus.ANSWERED

        plan = plan_turn(
            state,
            Analysis(
                kind=AnalysisKind.NORMAL_RESPONSE,
                facts={"answered_slot": SlotName.MOOD.value},
            ),
        )
        self.assertEqual(plan.action, PlannerAction.ASK_SLOT)
        self.assertEqual(plan.slot, SlotName.SLEEP)


class Wave2WaitFatigueTests(unittest.TestCase):
    def test_wait_request(self) -> None:
        state = _greeted_state()
        plan = plan_turn(state, Analysis(kind=AnalysisKind.WAIT_REQUEST))
        self.assertEqual(plan.action, PlannerAction.WAIT)

    def test_user_fatigue(self) -> None:
        state = _greeted_state()
        state.last_user_text = "я устал уже отвечать"
        plan = plan_turn(state, Analysis(kind=AnalysisKind.USER_FATIGUE))
        self.assertEqual(plan.action, PlannerAction.HANDLE_FATIGUE)


class Wave2AnswerUserTests(unittest.TestCase):
    def test_identity_question(self) -> None:
        state = _greeted_state()
        analysis = analyze_turn("кто вы?", state)
        plan = plan_turn(state, analysis)
        self.assertEqual(plan.action, PlannerAction.ANSWER_USER)
        self.assertEqual(plan.answer_type, AnswerType.IDENTITY)

    def test_why_calling(self) -> None:
        state = _greeted_state()
        analysis = analyze_turn("зачем вы звоните?", state)
        plan = plan_turn(state, analysis)
        self.assertEqual(plan.action, PlannerAction.ANSWER_USER)
        self.assertEqual(plan.answer_type, AnswerType.WHY_CALLING)

    def test_privacy(self) -> None:
        state = _greeted_state()
        analysis = analyze_turn("кто увидит мои ответы?", state)
        plan = plan_turn(state, analysis)
        self.assertEqual(plan.action, PlannerAction.ANSWER_USER)
        self.assertEqual(plan.answer_type, AnswerType.PRIVACY)


class Wave2RepairTests(unittest.TestCase):
    def test_repair_action(self) -> None:
        state = _greeted_state()
        state.pending_question = "Как вы спали этой ночью?"
        state.last_assistant_text = state.pending_question
        state.pending_slot = SlotName.SLEEP
        plan = plan_turn(state, Analysis(kind=AnalysisKind.REPAIR))
        self.assertEqual(plan.action, PlannerAction.REPAIR)


class Wave2CorrectionRefusalTests(unittest.TestCase):
    def test_correction(self) -> None:
        state = _greeted_state()
        analysis = analyze_turn("нет, не голова, спина", state)
        plan = plan_turn(state, analysis)
        self.assertEqual(plan.action, PlannerAction.HANDLE_CORRECTION)

    def test_refusal(self) -> None:
        state = _greeted_state()
        state.pending_slot = SlotName.MOOD
        analysis = analyze_turn("не хочу про настроение", state)
        plan = plan_turn(state, analysis)
        self.assertEqual(plan.action, PlannerAction.HANDLE_REFUSAL)
        self.assertEqual(plan.slot, SlotName.MOOD)


class Wave2SafetyTests(unittest.TestCase):
    def test_safety_blocks_agenda(self) -> None:
        state = _greeted_state()
        state.safety_phase = SafetyPhase.ACTIVE
        state.safety_active = True
        plan = plan_turn(state, Analysis(kind=AnalysisKind.NORMAL_RESPONSE))
        self.assertEqual(plan.action, PlannerAction.SAFETY)

    def test_distress_during_safety_stays_safety(self) -> None:
        state = _greeted_state()
        state.safety_phase = SafetyPhase.ACTIVE
        state.safety_active = True
        state.last_user_text = "мне очень страшно"
        plan = plan_turn(state, Analysis(kind=AnalysisKind.NORMAL_RESPONSE))
        self.assertEqual(plan.action, PlannerAction.SAFETY)


class Wave2SideQuestionResumeTests(unittest.TestCase):
    def test_side_question_then_resume_sleep(self) -> None:
        state = _greeted_state()
        state.slot_statuses[SlotName.WELLNESS] = SlotStatus.ANSWERED
        state.slot_statuses[SlotName.MOOD] = SlotStatus.ANSWERED
        state.pending_slot = SlotName.SLEEP
        state.current_topic = SlotName.SLEEP

        analysis = analyze_turn("а зачем вы вообще звоните?", state)
        plan = plan_turn(state, analysis)
        self.assertEqual(plan.action, PlannerAction.ANSWER_USER)
        self.assertEqual(plan.answer_type, AnswerType.WHY_CALLING)

        state.reduce_user_turn(
            "а зачем вы вообще звоните?",
            analysis.kind.value,
            analysis.facts,
        )
        self.assertEqual(state.pending_slot, SlotName.SLEEP)

        analysis2 = analyze_turn("нормально спал", state)
        state.reduce_user_turn(
            "нормально спал",
            analysis2.kind.value,
            analysis2.facts,
        )
        plan2 = plan_turn(state, analysis2)
        self.assertEqual(plan2.action, PlannerAction.ASK_SLOT)
        self.assertEqual(plan2.slot, SlotName.PLANS)
        self.assertNotEqual(plan2.slot, SlotName.MOOD)


class Wave2RepairAckTests(unittest.TestCase):
    def test_repair_ack_clears_pending(self) -> None:
        state = _greeted_state()
        state.repair_pending = True
        state.reduce_user_turn("ага, понял", "NORMAL_RESPONSE", {})
        self.assertFalse(state.repair_pending)


if __name__ == "__main__":
    unittest.main()
