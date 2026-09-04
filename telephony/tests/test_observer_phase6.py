"""Phase 6 — QuestionLedger, TurnDirective, heard ledger, local-only."""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation_system.domain.fsm_types import CallPhase
from conversation_system.integration.facade import ConversationFacade
from conversation_system.ledger.question_ledger import QuestionLedger, QuestionStatus
from conversation_system.reply.llm_context import compose_turn_directive
from adapters.cloud import LocalOnlyViolation, enforce_local_only


class QuestionLedgerTests(unittest.TestCase):
    def test_no_reask_answered_mood(self):
        ledger = QuestionLedger()
        rec = ledger.plan_slot("настроение", turn=1)
        ledger.mark_asked(rec.id, text="Как настроение?", turn=1)
        ledger.mark_heard(rec.id, turn=1)
        ledger.mark_answered("настроение", answer="бодрое", turn=2)
        self.assertFalse(ledger.can_ask_slot("настроение"))
        with self.assertRaises(ValueError):
            ledger.plan_slot("настроение", turn=3)

    def test_cancelled_on_barge_in_before_heard(self):
        ledger = QuestionLedger()
        rec = ledger.plan_slot("сон", turn=1)
        ledger.mark_asked(rec.id, text="Как спали?", turn=1, generation_id=7)
        ledger.mark_cancelled(generation_id=7)
        self.assertEqual(ledger.slot_status("сон"), QuestionStatus.CANCELLED)


class TurnDirectiveTests(unittest.TestCase):
    def test_required_slot_in_directive(self):
        text = compose_turn_directive(
            required_slot="сон",
            required_action="Спроси ТОЛЬКО о сне.",
            forbidden_slots=("настроение",),
        )
        self.assertIn("Required slot: сон", text)
        self.assertIn("Never repeat: настроение", text)


class HeardLedgerIntegrationTests(unittest.TestCase):
    def test_mark_segment_played_moves_asked_to_heard(self):
        facade = ConversationFacade()
        handle, _ = facade.begin_call(call_id="p6-heard", greeting_played=True)
        session = facade._get_session(handle)  # noqa: SLF001
        rec = session.question_ledger.plan_slot("настроение", turn=1)
        session.question_ledger.mark_asked(
            rec.id, text="Как настроение?", turn=1, generation_id=3)
        facade.mark_segment_played(
            handle, generation_id=3, segment_id="seg-0001.wav")
        self.assertEqual(
            session.question_ledger.slot_status("настроение"),
            QuestionStatus.HEARD,
        )

    def test_no_duplicate_mood_after_answered(self):
        facade = ConversationFacade()
        handle, _ = facade.begin_call(call_id="p6-mood", greeting_played=True)
        p1 = facade.plan_turn(handle, transcript="хорошо", stt_confidence=0.9)
        facade.commit_turn(handle, p1, p1.spoken_reply)
        p2 = facade.plan_turn(
            handle, transcript="бодрое настроение", stt_confidence=0.9)
        facade.commit_turn(handle, p2, "Рада слышать. Как настроение?")
        p3 = facade.plan_turn(
            handle, transcript="кто вы?", stt_confidence=0.9)
        facade.commit_turn(handle, p3, "Я Вера из Имвера.")
        resume = facade.plan_turn(handle, transcript="ясно", stt_confidence=0.9)
        session = facade._get_session(handle)  # noqa: SLF001
        intent = resume.meta.get("intent") or ""
        self.assertIn("сон", intent.lower())
        self.assertIn("Never repeat: настроение", intent)
        self.assertEqual(session.fsm.phase, CallPhase.GOOD_PATH)


class LocalOnlyTests(unittest.TestCase):
    def test_blocks_openai_llm_without_localhost(self):
        env = {
            "MOSS_LOCAL_ONLY": "1",
            "MOSS_LLM_PROVIDER": "openai",
            "MOSS_LLM_BASE_URL": "https://api.openai.com/v1",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with self.assertRaises(LocalOnlyViolation):
                enforce_local_only()

    def test_allows_localhost_openai(self):
        env = {
            "MOSS_LOCAL_ONLY": "1",
            "MOSS_LLM_PROVIDER": "openai",
            "MOSS_LLM_BASE_URL": "http://127.0.0.1:9500/v1",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            enforce_local_only()


if __name__ == "__main__":
    unittest.main()
