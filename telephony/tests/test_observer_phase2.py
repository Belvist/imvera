"""Phase 2 observer — CHOICE PendingQuestion integration."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation_system.domain.pending_question import (
    PendingQuestionType,
    infer_pending_from_prompt,
    validate_pending_answer,
)
from conversation_system.integration.facade import ConversationFacade


class ChoicePendingQuestionTests(unittest.TestCase):
    def test_infer_intensity_choice_from_symptom_probe(self):
        pq = infer_pending_from_prompt(
            "Понимаю. Как сейчас — боль сильная или терпимая?")
        self.assertIsNotNone(pq)
        self.assertEqual(pq.kind, PendingQuestionType.CHOICE)
        self.assertIn("сильная", pq.choices)
        self.assertIn("терпимая", pq.choices)

    def test_bare_da_rejected_on_intensity_choice(self):
        pq = infer_pending_from_prompt(
            "Понимаю. Как сейчас — боль сильная или терпимая?")
        assert pq is not None
        valid, reason = validate_pending_answer(pq, "да")
        self.assertFalse(valid)
        self.assertEqual(reason, "choice_needs_pick")

    def test_valid_choice_answer_accepted(self):
        pq = infer_pending_from_prompt(
            "Понимаю. Как сейчас — боль сильная или терпимая?")
        assert pq is not None
        valid, _ = validate_pending_answer(pq, "терпимо")
        self.assertTrue(valid)


class AmbiguousDaIntegrationTests(unittest.TestCase):
    def test_bare_da_after_symptom_reasks_choice(self):
        facade = ConversationFacade()
        handle, _ = facade.begin_call(call_id="phase2", greeting_played=True)
        for text in ("плохо", "голова болит", "да"):
            plan = facade.plan_turn(
                handle, transcript=text, stt_confidence=0.9)
            facade.commit_turn(handle, plan, plan.spoken_reply)
        self.assertIn("?", plan.spoken_reply)
        self.assertNotIn("записала", plan.spoken_reply.lower())


if __name__ == "__main__":
    unittest.main()
