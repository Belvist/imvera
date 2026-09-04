"""Analyzer unit tests — permanent MUST PASS regression suite."""
from __future__ import annotations

import unittest

from golden_path.analyzer import AnalysisKind, AnswerType, analyze_turn
from golden_path.slots import SlotName, SlotStatus
from golden_path.state import ConversationState


class AnalyzerTests(unittest.TestCase):
    def test_correction_spine(self) -> None:
        state = ConversationState()
        analysis = analyze_turn("не голова, а спина", state)
        self.assertEqual(analysis.kind, AnalysisKind.CORRECTION)
        self.assertEqual(analysis.facts.get("symptom"), "back")

    def test_correction_head_to_back(self) -> None:
        state = ConversationState()
        analysis = analyze_turn("нет, не голова, спина", state)
        self.assertEqual(analysis.kind, AnalysisKind.CORRECTION)
        self.assertEqual(analysis.facts.get("symptom"), "back")

    def test_repair(self) -> None:
        state = ConversationState()
        analysis = analyze_turn("что вы сказали?", state)
        self.assertEqual(analysis.kind, AnalysisKind.REPAIR)

    def test_safety(self) -> None:
        state = ConversationState()
        analysis = analyze_turn("мне трудно дышать", state)
        self.assertEqual(analysis.kind, AnalysisKind.SAFETY)

    def test_user_question(self) -> None:
        state = ConversationState()
        analysis = analyze_turn("кто вы такая?", state)
        self.assertEqual(analysis.kind, AnalysisKind.DIRECT_USER_QUESTION)
        self.assertEqual(analysis.answer_type, AnswerType.IDENTITY)

    def test_why_calling_answer_type(self) -> None:
        analysis = analyze_turn("зачем вы звоните?", ConversationState())
        self.assertEqual(analysis.answer_type, AnswerType.WHY_CALLING)

    def test_spal_horosho_is_sleep(self) -> None:
        analysis = analyze_turn("спал хорошо", ConversationState())
        self.assertEqual(analysis.facts.get("answered_slot"), SlotName.SLEEP.value)

    def test_nastroenie_horoshee_is_mood(self) -> None:
        analysis = analyze_turn("настроение хорошее", ConversationState())
        self.assertEqual(analysis.facts.get("answered_slot"), SlotName.MOOD.value)

    def test_normally_pending_wellness(self) -> None:
        state = ConversationState()
        state.pending_slot = SlotName.WELLNESS
        analysis = analyze_turn("нормально", state)
        self.assertEqual(analysis.facts.get("answered_slot"), SlotName.WELLNESS.value)

    def test_normally_pending_sleep(self) -> None:
        state = ConversationState()
        state.pending_slot = SlotName.SLEEP
        analysis = analyze_turn("нормально", state)
        self.assertEqual(analysis.facts.get("answered_slot"), SlotName.SLEEP.value)

    def test_wait_request(self) -> None:
        analysis = analyze_turn("секундочку, я вспомню", ConversationState())
        self.assertEqual(analysis.kind, AnalysisKind.WAIT_REQUEST)

    def test_weather_question_not_wait_request(self) -> None:
        analysis = analyze_turn("кстати какая сегодня погода у вас?", ConversationState())
        self.assertEqual(analysis.kind, AnalysisKind.DIRECT_USER_QUESTION)

    def test_user_fatigue(self) -> None:
        analysis = analyze_turn("я устал уже отвечать", ConversationState())
        self.assertEqual(analysis.kind, AnalysisKind.USER_FATIGUE)

    def test_nothing_special_plans_not_correction(self) -> None:
        analysis = analyze_turn("ничего особенного не планирую", ConversationState())
        self.assertNotEqual(analysis.kind, AnalysisKind.CORRECTION)
        self.assertEqual(analysis.facts.get("answered_slot"), SlotName.PLANS.value)

    def test_narrative_knee_symptom_without_wellness_slot(self) -> None:
        text = (
            "вчера внучка приезжала, картошки привезла, "
            "а вечером колено заболело"
        )
        analysis = analyze_turn(text, ConversationState())
        self.assertEqual(analysis.facts.get("symptom"), "knee")
        self.assertNotEqual(analysis.facts.get("answered_slot"), SlotName.WELLNESS.value)
        self.assertIsNone(analysis.facts.get("answered_slot"))

    def test_sekundochku_not_plans(self) -> None:
        analysis = analyze_turn("секундочку, я вспомню", ConversationState())
        self.assertIsNone(analysis.facts.get("answered_slot"))
        self.assertNotEqual(analysis.facts.get("answered_slot"), SlotName.PLANS.value)


class AnalyzerStateReducerSlotTests(unittest.TestCase):
    """Slot closure via detect_slot_answer used by state reducer."""

    def test_apply_normally_marks_wellness_answered(self) -> None:
        state = ConversationState()
        state.pending_slot = SlotName.WELLNESS
        analysis = analyze_turn("нормально", state)
        state.reduce_user_turn(
            "нормально",
            analysis.kind.value,
            analysis.facts,
        )
        self.assertEqual(state.slot_statuses[SlotName.WELLNESS], SlotStatus.ANSWERED)


if __name__ == "__main__":
    unittest.main()
