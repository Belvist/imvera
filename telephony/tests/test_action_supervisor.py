"""ActionSupervisor — block unverified family-delivery claims before TTS."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation_system.ledger.action_supervisor import (
    ActionSupervisor,
    sanitize_delivery_claim,
)
from conversation_system.reply.guards import sanitize_segment
from conversation_system.reply.spoken import resolve_spoken_reply
from core.call_mirror import CallMirror


class ActionSupervisorUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.supervisor = ActionSupervisor()

    def test_blocks_peredala_blizkim(self) -> None:
        out = self.supervisor.sanitize("Я уже передала близким.")
        self.assertNotIn("передал", out.lower())
        self.assertIn("записал", out.lower())

    def test_blocks_opovestila(self) -> None:
        out = self.supervisor.sanitize("Я оповестила родных.")
        self.assertNotIn("оповест", out.lower())
        self.assertIn("записал", out.lower())

    def test_blocks_uzhe_vidyat(self) -> None:
        out = self.supervisor.sanitize("Близкие уже видят.")
        self.assertNotIn("уже видят", out.lower())
        self.assertIn("записал", out.lower())

    def test_allows_safe_record_phrase(self) -> None:
        safe = "Я всё записала, близкие увидят."
        self.assertEqual(self.supervisor.sanitize(safe), safe)

    def test_shared_helper_uses_fallback(self) -> None:
        fb = "Как настроение сегодня?"
        out = sanitize_delivery_claim(
            "Уже передала родным.",
            fallback=fb,
        )
        self.assertEqual(out, fb)


class ResolveSpokenReplyDeliveryTests(unittest.TestCase):
    def test_fake_delivery_never_in_resolve_spoken_reply(self) -> None:
        mirror = CallMirror()
        plan = {
            "allow_llm": True,
            "fallback": "Как настроение сегодня?",
            "text": "хорошо",
        }
        spoken = resolve_spoken_reply(
            mirror,
            plan,
            "Хорошо, я уже передала близким.",
        )
        low = spoken.lower()
        self.assertNotIn("передал", low)
        self.assertNotIn("близким", low)

    def test_orchestrator_segment_path_blocks_delivery(self) -> None:
        fb = "Как спали ночью?"
        segment = "Отлично, я оповестила их."
        guarded = sanitize_segment(
            segment,
            fallback=fb,
            transcript="хорошо",
            llm_generated=True,
        )
        guarded = sanitize_delivery_claim(guarded, fallback=fb)
        low = guarded.lower()
        self.assertNotIn("оповест", low)
        self.assertNotIn("передал", low)


if __name__ == "__main__":
    unittest.main()
