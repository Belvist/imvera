"""Unified STT gate tests."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.stt_gates import gate_stt_transcript  # noqa: E402
from core.vocab import repair_fall_miscue  # noqa: E402


class SttGatesTests(unittest.TestCase):
    def test_low_conf_blank(self):
        text, reason = gate_stt_transcript("тортичина", 0.40)
        self.assertEqual(text, "")
        self.assertEqual(reason, "low_conf")

    def test_short_wellness_survives_low_conf(self):
        text, reason = gate_stt_transcript("хорошо", 0.12)
        self.assertEqual(text, "хорошо")
        self.assertIsNone(reason)

        text, reason = gate_stt_transcript("плохо", 0.05)
        self.assertEqual(text, "плохо")
        self.assertIsNone(reason)

    def test_garbage_blank(self):
        text, reason = gate_stt_transcript("Торатичина", 0.90)
        self.assertEqual(text, "")
        self.assertEqual(reason, "low_conf")

    def test_mid_conf_confirm(self):
        text, reason = gate_stt_transcript("да всё хорошо", 0.65)
        self.assertEqual(text, "да всё хорошо")
        self.assertEqual(reason, "stt_uncertain")

    def test_high_conf_passes(self):
        text, reason = gate_stt_transcript("да всё хорошо", 0.90)
        self.assertEqual(text, "да всё хорошо")
        self.assertIsNone(reason)

    def test_fall_miscue_repaired(self):
        raw = "у палок не ударилось"
        text, reason = gate_stt_transcript(raw, 0.90)
        self.assertIn("упал", text)
        self.assertIsNone(reason)

    def test_repair_fall_miscue_unit(self):
        self.assertIn("упал", repair_fall_miscue("у палок не ударилось"))
        self.assertEqual(repair_fall_miscue("я упала"), "я упала")


class SttUncertainPlanTests(unittest.TestCase):
    def test_plan_reply_confirms_mid_conf(self):
        from core.dialogue import Agent

        agent = Agent(llm=None)
        plan = agent.plan_reply("может быть", reason="stt_uncertain")
        self.assertIn("услышала", (plan.get("fallback") or "").lower())
        self.assertIsNone(plan.get("intent"))

    def test_plan_reply_short_wellness_skips_confirm(self):
        from core.dialogue import Agent

        agent = Agent(llm=None)
        agent.start_check_in()
        plan = agent.plan_reply("хорошо", reason="stt_uncertain")
        self.assertNotIn("услышала", (plan.get("fallback") or "").lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
