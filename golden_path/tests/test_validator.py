"""Validator unit tests."""
from __future__ import annotations

import unittest

from golden_path.planner import PlannerAction
from golden_path.slots import SlotName
from golden_path.state import ConversationState
from golden_path.validator import validate_reply


class ValidatorTests(unittest.TestCase):
    def test_banned_davayte(self) -> None:
        state = ConversationState()
        state.turns_since_question = 2
        res = validate_reply("Давайте перейдём к сну", PlannerAction.ACK_ONLY, state)
        self.assertFalse(res.ok)

    def test_no_reask_answered_slot(self) -> None:
        state = ConversationState()
        state.slot_statuses[SlotName.MOOD] = __import__(
            "golden_path.slots", fromlist=["SlotStatus"]
        ).SlotStatus.ANSWERED
        state.turns_since_question = 2
        res = validate_reply(
            "Как у вас настроение?",
            PlannerAction.ASK_SLOT,
            state,
            slot=SlotName.MOOD,
        )
        self.assertFalse(res.ok)

    def test_ask_slot_double_question_uses_fallback(self) -> None:
        state = ConversationState()
        from golden_path.slots import SlotStatus

        state.slot_statuses[SlotName.WELLNESS] = SlotStatus.ANSWERED
        state.slot_statuses[SlotName.MOOD] = SlotStatus.ANSWERED
        state.slot_statuses[SlotName.SLEEP] = SlotStatus.ANSWERED
        raw = "Вы проснулись отдохнувшим? Какие у вас планы на сегодня?"
        res = validate_reply(
            raw,
            PlannerAction.ASK_SLOT,
            state,
            slot=SlotName.PLANS,
            apply_fallback=True,
        )
        self.assertTrue(res.used_fallback)
        self.assertIn("too_many_questions", res.violations)
        self.assertEqual(res.text.count("?"), 1)
        self.assertIn("план", res.text.lower())


if __name__ == "__main__":
    unittest.main()
