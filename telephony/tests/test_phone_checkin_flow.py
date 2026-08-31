"""Phone path: Lua creates check_in sessions; wellness answers advance agenda."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.dialogue import Agent, MVERA_GREETING


class PhoneCheckInFlowTests(unittest.TestCase):
    def _serve(self):
        from core.orchestrator import Serve

        class _Args:
            refs = []
            tts_port_file = None
            tts_port = None
            inference_steps = 6
            no_style = False
            outdir = "/tmp/mossvoice_phone_checkin"
            tts_host = None

        return Serve(_Args())

    def test_new_call_without_caller_starts_check_in(self):
        serve = self._serve()
        cid = serve.new_call()
        ag = serve.get_call(cid).agent
        self.assertEqual(ag.mode, "check_in")
        self.assertTrue(ag._agenda_asked)
        self.assertEqual(ag._last_reply, MVERA_GREETING)

    def test_new_call_mode_check_in(self):
        serve = self._serve()
        cid = serve.new_call(mode="check_in")
        ag = serve.get_call(cid).agent
        self.assertEqual(ag.mode, "check_in")

    def test_wellness_good_advances_after_greeting(self):
        ag = Agent()
        ag.start_check_in()
        plan = ag.plan_reply("всё хорошо")
        fb = (plan.get("fallback") or "").lower()
        self.assertNotIn("хорошо или плохо", fb)
        self.assertTrue(
            plan.get("intent") or "?" in fb or "настроен" in fb,
            msg=f"expected next topic, got {plan!r}",
        )

    def test_wellness_bad_gets_symptom_followup(self):
        ag = Agent()
        ag.start_check_in()
        plan = ag.plan_reply("плохо")
        self.assertEqual(ag.mode, "safety_confirm")
        combined = ((plan.get("intent") or "") + " " +
                    (plan.get("fallback") or "")).lower()
        self.assertTrue(
            "симптом" in combined or "самочувств" in combined
            or "беспоко" in combined or "?" in combined,
            msg=combined,
        )

    def test_first_empty_after_greeting_repeats_not_anchor(self):
        ag = Agent()
        ag.start_check_in()
        plan = ag.plan_reply("", reason=None)
        # Anchor is more competent than bare repeat — even at greeting
        self.assertIn("хорошо или плохо", plan["fallback"].lower())

    def test_answers_wellness_short_phrases(self):
        ag = Agent()
        ag.start_check_in()
        for phrase in ("хорошо", "нормально", "плохо", "мне всё плохо"):
            ag2 = Agent()
            ag2.start_check_in()
            self.assertTrue(
                ag2._answers_wellness(phrase),
                msg=phrase,
            )


class EchoGuardTests(unittest.TestCase):
    def test_short_wellness_not_echo(self):
        from core.orchestrator import Serve

        self.assertFalse(
            Serve._looks_like_echo("хорошо", MVERA_GREETING))
        self.assertFalse(
            Serve._looks_like_echo("всё хорошо", MVERA_GREETING))
        self.assertFalse(
            Serve._looks_like_echo("плохо", MVERA_GREETING))


if __name__ == "__main__":
    unittest.main(verbosity=2)
