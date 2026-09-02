"""ROADMAP E2: family call statuses + DTMF fallback."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.call_status import (  # noqa: E402
    CallStatus, SCENARIO_VERSION, SAFETY_RULES_VERSION,
    from_agent_outcome, resolve_family_status, build_reasons,
    summary_for_family, family_fields_for_finalize,
)
from core.dtmf import (  # noqa: E402
    DTMF_PROMPT, DtmfEvent, interpret_dtmf, should_offer_dtmf,
)
from core.dialogue import Agent  # noqa: E402


class CallStatusMappingTests(unittest.TestCase):
    def test_all_six_statuses_constructible(self):
        values = {s.value for s in CallStatus}
        self.assertEqual(values, {
            "green", "yellow", "red", "no_contact", "technical", "declined",
        })
        for s in CallStatus:
            self.assertIsInstance(s, CallStatus)

    def test_from_agent_outcome_mapping(self):
        self.assertEqual(from_agent_outcome("ok"), CallStatus.GREEN)
        self.assertEqual(from_agent_outcome("attention"), CallStatus.YELLOW)
        self.assertEqual(from_agent_outcome("alert"), CallStatus.RED)
        self.assertEqual(from_agent_outcome("unknown"), CallStatus.TECHNICAL)
        self.assertEqual(from_agent_outcome("no_speech"), CallStatus.NO_CONTACT)
        self.assertEqual(from_agent_outcome("no_contact"), CallStatus.NO_CONTACT)
        self.assertEqual(from_agent_outcome("declined"), CallStatus.DECLINED)
        self.assertEqual(from_agent_outcome("technical"), CallStatus.TECHNICAL)
        self.assertEqual(from_agent_outcome("bogus"), CallStatus.TECHNICAL)

    def test_alert_path_never_becomes_technical_without_error(self):
        self.assertEqual(
            resolve_family_status("alert"), CallStatus.RED)
        fields = family_fields_for_finalize("alert", notes=["опасно"])
        self.assertEqual(fields["family_status"], "red")
        self.assertIsNone(fields["technical_error"])
        self.assertIn("тревожн", fields["summary_for_family"].lower())

    def test_technical_error_overrides_green(self):
        fields = family_fields_for_finalize(
            "ok", notes=["всё хорошо"], technical_error="stt:RuntimeError")
        self.assertEqual(fields["family_status"], "technical")
        self.assertNotEqual(fields["family_status"], "green")
        self.assertEqual(fields["technical_error"], "stt:RuntimeError")
        self.assertEqual(fields["scenario_version"], SCENARIO_VERSION)
        self.assertEqual(fields["safety_rules_version"], SAFETY_RULES_VERSION)

    def test_declined_and_no_contact(self):
        self.assertEqual(
            resolve_family_status("ok", declined=True), CallStatus.DECLINED)
        self.assertEqual(
            resolve_family_status("unknown", no_contact=True),
            CallStatus.NO_CONTACT)


class SummaryAndReasonsTests(unittest.TestCase):
    def test_summary_is_short_russian_no_transcript_dump(self):
        long_transcript = " ".join(["слово"] * 80)
        summary = summary_for_family(
            notes=["приняла лекарства"],
            facts=["настроение хорошее"],
            status=CallStatus.GREEN,
        )
        self.assertIsInstance(summary, str)
        self.assertGreaterEqual(summary.count("."), 1)
        self.assertLessEqual(len(summary), 400)
        self.assertNotIn(long_transcript, summary)
        self.assertIn("порядке", summary.lower())

    def test_summary_per_status(self):
        for status in CallStatus:
            text = summary_for_family(notes=[], facts=[], status=status)
            self.assertTrue(text.strip())
            self.assertLess(len(text.split()), 80)

    def test_build_reasons(self):
        reasons = build_reasons(
            notes=["плохое самочувствие"],
            facts=["головная боль"],
            status=CallStatus.YELLOW,
            technical_error=None,
        )
        self.assertTrue(any(r.startswith("status:yellow") for r in reasons))
        self.assertTrue(any("плохое" in r for r in reasons))
        self.assertTrue(any("головн" in r for r in reasons))


class DtmfTests(unittest.TestCase):
    def test_interpret_dtmf(self):
        self.assertEqual(interpret_dtmf("1"), DtmfEvent.OK)
        self.assertEqual(interpret_dtmf("2"), DtmfEvent.HELP)
        self.assertEqual(interpret_dtmf("DTMF 1"), DtmfEvent.OK)
        self.assertEqual(interpret_dtmf("9"), DtmfEvent.UNKNOWN)
        self.assertEqual(interpret_dtmf(""), DtmfEvent.UNKNOWN)

    def test_should_offer_after_two_empty(self):
        self.assertFalse(should_offer_dtmf(1))
        self.assertTrue(should_offer_dtmf(2))
        self.assertTrue(should_offer_dtmf(5))

    def test_agent_offers_dtmf_after_two_empty(self):
        a = Agent(llm=None)
        a.start_check_in()
        a.observe_confidence(0.9)
        p1 = a.plan_reply("", reason="low_conf")
        self.assertNotIn("нажмите 1", p1["fallback"].lower())
        p2 = a.plan_reply("", reason="low_conf")
        self.assertIn("нажмите 1", p2["fallback"].lower())
        self.assertIn("нажмите 2", p2["fallback"].lower())
        self.assertEqual(p2["fallback"], DTMF_PROMPT)
        self.assertTrue(a._dtmf_offered)

    def test_handle_dtmf_ok_and_help(self):
        a = Agent(llm=None)
        a.start_check_in()
        a.observe_confidence(0.9)
        p = a.handle_dtmf("1")
        self.assertTrue(p.get("fallback") or p.get("intent"))
        a2 = Agent(llm=None)
        a2.start_check_in()
        a2.observe_confidence(0.9)
        p2 = a2.handle_dtmf("2")
        self.assertIn(a2.status, ("attention", "alert", "ok", "unknown"))
        self.assertTrue(p2.get("fallback") or p2.get("intent"))

    def test_mark_technical_blocks_green(self):
        a = Agent(llm=None)
        a.status = "ok"
        a.mark_technical("llm:Timeout")
        self.assertEqual(a.status, "technical")
        self.assertEqual(a.technical_error, "llm:Timeout")
        fields = family_fields_for_finalize(
            a.status, notes=a.notes, technical_error=a.technical_error)
        self.assertEqual(fields["family_status"], "technical")


if __name__ == "__main__":
    unittest.main()
