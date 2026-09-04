"""Spoken FINAL output quality — permanent regression tests."""
from __future__ import annotations

import unittest

from golden_path.planner import PlannerAction
from golden_path.slots import SlotName, SlotStatus
from golden_path.spoken_quality import KNOWN_BAD_FINALS, check_spoken_quality
from golden_path.state import ConversationState
from golden_path.validator import validate_reply


class SpokenQualityTests(unittest.TestCase):
    def test_known_bad_phrases_fail(self) -> None:
        for phrase in KNOWN_BAD_FINALS:
            violations = check_spoken_quality(phrase)
            self.assertTrue(
                violations,
                msg=f"expected violations for: {phrase!r}",
            )

    def test_good_ask_sleep_passes(self) -> None:
        self.assertEqual(check_spoken_quality("Как вы спали этой ночью?"), [])

    def test_latin_rejected(self) -> None:
        self.assertIn("latin_in_russian", check_spoken_quality("Вы спали last night?"))

    def test_instruction_leak_rejected(self) -> None:
        self.assertIn(
            "instruction_leakage",
            check_spoken_quality("Попрощайтесь, ничего не планируете."),
        )

    def test_assistant_male_self_rejected(self) -> None:
        self.assertIn(
            "assistant_masculine_self",
            check_spoken_quality("Я уже устал, давайте закончим."),
        )

    def test_unconfirmed_action_claim_rejected(self) -> None:
        self.assertIn(
            "unconfirmed_action_claim",
            check_spoken_quality("Я всё записала, близкие увидят."),
        )
        self.assertIn(
            "unconfirmed_action_claim",
            check_spoken_quality(
                "Мы звоним, чтобы узнать, как вы себя чувствуете, "
                "и передать близким, если им будет важно."
            ),
        )

    def test_user_gender_sleep_rejected(self) -> None:
        self.assertIn(
            "user_gender_guess",
            check_spoken_quality("Как прошлую ночь спал?"),
        )

    def test_perception_rejected(self) -> None:
        self.assertIn(
            "hallucinated_perception",
            check_spoken_quality("Вы выглядите уставшим."),
        )

    def test_internal_enum_rejected(self) -> None:
        self.assertIn(
            "internal_label_leak",
            check_spoken_quality("Вы хотите подтвердить symptom knee?"),
        )

    def test_close_deterministic_not_instruction(self) -> None:
        state = ConversationState()
        state.slot_statuses[SlotName.PLANS] = SlotStatus.ANSWERED
        res = validate_reply(
            "Попрощайтесь, ничего не планируете.",
            PlannerAction.CLOSE,
            state,
            apply_fallback=True,
        )
        self.assertTrue(res.used_fallback)
        self.assertIn("берегите", res.text.lower())

    def test_correction_deterministic_no_question(self) -> None:
        state = ConversationState()
        state.facts["symptom"] = "back"
        res = validate_reply(
            "Вы говорите, что симптом — это спину?",
            PlannerAction.HANDLE_CORRECTION,
            state,
            apply_fallback=True,
        )
        self.assertTrue(res.used_fallback)
        self.assertIn("спин", res.text.lower())
        self.assertNotIn("?", res.text)

    def test_repair_repeats_last_question(self) -> None:
        state = ConversationState()
        state.pending_question = "Какое у вас сегодня настроение?"
        res = validate_reply(
            "Что вас интересует?",
            PlannerAction.REPAIR,
            state,
            apply_fallback=True,
        )
        self.assertEqual(res.text, "Какое у вас сегодня настроение?")


if __name__ == "__main__":
    unittest.main()
