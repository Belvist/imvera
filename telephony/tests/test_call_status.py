"""ROADMAP E2: family call statuses + silence ladder."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.call_status import (  # noqa: E402
    CallStatus, SCENARIO_VERSION, SAFETY_RULES_VERSION,
    from_agent_outcome, resolve_family_status, build_reasons,
    summary_for_family, family_fields_for_finalize,
)
from core.call_mirror import CallMirror  # noqa: E402
from core.conversation_v2_bridge import begin_v2_call, plan_turn_for_call
from core.state import CallContext  # noqa: E402


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


class SilenceLadderTests(unittest.TestCase):
    def _ctx(self):
        ctx = CallContext(call_id="silence-test", agent=CallMirror())
        begin_v2_call(ctx)
        return ctx

    def test_facade_never_offers_dtmf(self):
        ctx = self._ctx()
        p1, _ = plan_turn_for_call(
            ctx, ctx.agent, transcript="", reason="low_conf", stt_confidence=0.9)
        self.assertNotIn("нажмите 1", p1["fallback"].lower())
        p2, _ = plan_turn_for_call(
            ctx, ctx.agent, transcript="", reason="low_conf", stt_confidence=0.9)
        self.assertNotIn("нажмите 1", p2["fallback"].lower())
        self.assertNotIn("нажмите 2", p2["fallback"].lower())

    def test_silence_ladder_has_spoken_fallback(self):
        ctx = self._ctx()
        plan, _ = plan_turn_for_call(
            ctx, ctx.agent, transcript="", reason="low_conf", stt_confidence=0.9)
        self.assertTrue((plan.get("fallback") or "").strip())

    def test_mark_technical_blocks_green(self):
        a = CallMirror(llm=None)
        a.status = "ok"
        a.mark_technical("llm:Timeout")
        self.assertEqual(a.status, "technical")
        self.assertEqual(a.technical_error, "llm:Timeout")
        fields = family_fields_for_finalize(
            a.status, notes=a.notes, technical_error=a.technical_error)
        self.assertEqual(fields["family_status"], "technical")


if __name__ == "__main__":
    unittest.main()
