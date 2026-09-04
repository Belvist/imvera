"""Phase 1 observer / pending_question tests."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation_system.domain.pending_question import (
    PendingQuestion,
    PendingQuestionType,
    infer_pending_from_prompt,
    validate_pending_answer,
)
from conversation_system.domain.understanding import (
    ConfidenceBand,
    SpeechAct,
    SttReason,
    TurnUnderstanding,
)
from conversation_system.memory.state import ConversationMemory
from conversation_system.observer import Observer
from conversation_system.variety.dedupe import VarietyEngine


class PendingQuestionTests(unittest.TestCase):
    def test_choice_rejects_bare_da(self):
        pq = PendingQuestion(
            kind=PendingQuestionType.CHOICE,
            prompt="Утром или вечером болит?",
            choices=("утром", "вечером"),
        )
        valid, reason = validate_pending_answer(pq, "да")
        self.assertFalse(valid)
        self.assertEqual(reason, "choice_needs_pick")

    def test_yes_no_accepts_da(self):
        pq = PendingQuestion(
            kind=PendingQuestionType.YES_NO,
            prompt="Вам плохо?",
        )
        valid, _ = validate_pending_answer(pq, "да")
        self.assertTrue(valid)

    def test_infer_choice_from_prompt(self):
        pq = infer_pending_from_prompt("Болит утром или вечером?")
        self.assertIsNotNone(pq)
        self.assertEqual(pq.kind, PendingQuestionType.CHOICE)
        self.assertIn("утром", pq.choices)
        self.assertIn("вечером", pq.choices)


class ObserverTests(unittest.TestCase):
    def test_why_call_sets_directive(self):
        mem = ConversationMemory(call_id="t")
        obs = Observer()
        u = TurnUnderstanding(
            raw_text="зачем вы звоните?",
            clean_text="зачем вы звоните?",
            input_reason=SttReason.NONE,
            speech_act=SpeechAct.QUESTION,
            topic_signals=(),
            symptom_focus=None,
            answers_last_control=None,
            confidence_band=ConfidenceBand.HIGH,
            is_narrative=False,
            word_count=3,
        )
        patch = obs.observe_turn(mem, u)
        self.assertIn("Имвера", patch.next_directive)
        self.assertEqual(len(patch.unanswered_user_questions), 1)

    def test_correction_detected(self):
        mem = ConversationMemory(call_id="t", active_symptom="голова")
        obs = Observer()
        u = TurnUnderstanding(
            raw_text="нет не голова спина болит",
            clean_text="нет не голова спина болит",
            input_reason=SttReason.NONE,
            speech_act=SpeechAct.SYMPTOM,
            topic_signals=(),
            symptom_focus="спина",
            answers_last_control=None,
            confidence_band=ConfidenceBand.HIGH,
            is_narrative=False,
            word_count=5,
            mentions_symptom=True,
        )
        patch = obs.observe_turn(mem, u)
        self.assertTrue(patch.corrections or patch.memory_patches)


class VarietyIsolationTests(unittest.TestCase):
    def test_no_global_pollution(self):
        a = VarietyEngine()
        b = VarietyEngine()
        a.remember("фраза уникальная альфа")
        picked = b.pick_from_pool(("фраза уникальная альфа", "другая"), pool_key="t")
        self.assertEqual(picked, "фраза уникальная альфа")


if __name__ == "__main__":
    unittest.main()
