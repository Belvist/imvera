"""Live post-mortem regressions (calls 8f650, 9b01 — 2026-08-30)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.stt import confidence_from_result  # noqa: E402
from core.dialogue import Agent  # noqa: E402
from core.safety_engine import Observation, SafetyEngine  # noqa: E402


class _FakeResult:
    def __init__(self, text="", speech_s=None, segments=()):
        self.text = text
        self.speech_s = speech_s
        self.segments = segments


class QwenConfidenceTests(unittest.TestCase):
    """9b01: 68-char turn must not score 0.35 on absurd token/speech rate."""

    def test_long_real_speech_not_pinned_low(self):
        text = (
            "Привет, чувствую себя сейчас хорошо, "
            "до этого чувствовал себя плохо"
        )
        res = _FakeResult(text=text, speech_s=1.76)
        # energy gate stubbed via speech path — use a loud-enough fake wav
        import struct
        import tempfile
        import wave

        fd, p = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        body = struct.pack("<8000h", *([8000] * 8000))
        with wave.open(p, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(body)
        try:
            conf = confidence_from_result(p, res)
            self.assertGreaterEqual(conf, 0.78, msg=f"got {conf}")
        finally:
            os.remove(p)


class GratitudeBackchannelTests(unittest.TestCase):
    """8f650 T2: «Супер, спасибо» on open control ≠ uncertain_red."""

    def test_gratitude_clears_awaiting_as_unknown(self):
        eng = SafetyEngine()
        eng.observe(Observation(raw_text="плохо", confidence=0.9))
        ev = eng.observe(
            Observation(raw_text="Супер, спасибо", confidence=0.35))
        self.assertEqual(ev.kind, "unknown")

    def test_gratitude_not_uncertain_on_low_conf(self):
        eng = SafetyEngine()
        eng.observe(Observation(raw_text="плохо", confidence=0.9))
        ev = eng.observe(Observation(raw_text="спасибо", confidence=0.1))
        self.assertNotEqual(ev.kind, "uncertain_red")


class SymptomWithUnknownTests(unittest.TestCase):
    """9b01 T2: headache must trigger symptom follow-up, not generic."""

    def test_ne_znayu_headache_is_possible_red(self):
        ev = SafetyEngine().observe(
            Observation(raw_text="Не знаю, но голова болела", confidence=0.35))
        self.assertEqual(ev.kind, "possible_red")

    def test_dialogue_symptom_on_unknown_topic(self):
        ag = Agent(llm=None)
        ag.start_check_in()
        # Advance past самочувствие so agenda sits on a later topic.
        ag.plan_reply("всё хорошо")
        ag.plan_reply("нормально")
        plan = ag.plan_reply("Не знаю, но голова как-то болела")
        combined = ((plan.get("intent") or "") + " " +
                    (plan.get("fallback") or "")).lower()
        self.assertTrue(
            "голов" in combined or "симптом" in combined
            or "самочувств" in combined,
            msg=combined,
        )

    def test_uncertain_after_control_reasks_symptom(self):
        """8f650: after «плохо» control, low-conf thanks → symptom not «настаивать»."""
        ag = Agent(llm=None)
        ag.start_check_in()
        ag.plan_reply("плохо")
        self.assertTrue(ag._clearing)
        ag.observe_confidence(0.35)
        plan = ag.plan_reply("Супер, спасибо")
        combined = ((plan.get("intent") or "") + " " +
                    (plan.get("fallback") or "")).lower()
        self.assertNotIn("настаивать", combined, msg=combined)
        self.assertTrue(
            "голов" in combined or "симптом" in combined
            or "самочувств" in combined or "беспоко" in combined,
            msg=combined,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
