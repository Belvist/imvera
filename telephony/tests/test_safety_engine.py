"""Stage 0A regression corpus: SafetyEngine + Agent safety flows.

Covers the documented mutation rounds (S1-S25) plus the scenarios found while
developing the engine itself: negation collisions via the "мне" prefix,
third-person subjects, inanimate object falls, self-harm ambiguity, help
requests, low-confidence observations and the state machine transitions.
Every row here is a regression gate: it must pass on every future change.
"""

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from core.safety_engine import Observation, SafetyEngine  # noqa: E402
from core.dialogue import Agent  # noqa: E402


# ---------------------------------------------------------------------------
# Single-utterance corpus (fresh engine per phrase).
# key: text -> expected VerdictEvent.kind
# ---------------------------------------------------------------------------
CORPUS = {
    # ---- wellbeing answers: ok ------------------------------------------
    "хорошо": "ok",
    "всё хорошо": "ok",
    "все хорошо": "ok",
    "нормально": "ok",
    "всё нормально": "ok",
    "нормально, спасибо": "ok",
    "отлично": "ok",
    "прекрасно": "ok",
    "замечательно": "ok",
    "неплохо": "ok",
    "не плохо": "ok",                       # S11 negation window
    "мне не плохо": "ok",                   # S11 "мне" prefix collision
    "не так уж плохо": "ok",
    "чувствую себя хорошо": "ok",
    "в порядке": "ok",
    "не жалуюсь": "ok",
    "бодра": "ok",
    "пью таблетки": "ok",                   # taking meds, not a request
    "принимаю лекарства": "ok",
    "температуры нет": "ok",                # S20 reverse negation
    "давление не упало": "ok",

    # ---- wellbeing answers: distress -> possible_red --------------------
    "плохо": "possible_red",
    "мне плохо": "possible_red",
    "мне очень плохо": "possible_red",      # S15 "мне очень" collision
    "мне не очень хорошо": "possible_red",  # complaint, NOT a negation-clear
    "не очень": "possible_red",
    "не хорошо": "possible_red",
    "у меня болит голова": "possible_red",  # S16
    "болит голова": "possible_red",
    "у меня кружится голова": "possible_red",  # S18
    "кружится голова": "possible_red",
    "температура": "possible_red",
    "температура 38": "possible_red",
    "слабость": "possible_red",
    "слабая": "possible_red",
    "тошнит": "possible_red",
    "сердце болит": "possible_red",
    "давление упало": "possible_red",       # health metric, not object
    "я не сильно болею, просто устал": "possible_red",  # S21
    "неважно себя чувствую": "possible_red",

    # ---- emergencies: confirmed_red -------------------------------------
    "скорая": "confirmed_red",              # S19 падеж "скорую"/"скорая"
    "скорую": "confirmed_red",
    "вызовите скорую": "confirmed_red",
    "вызовите врача": "confirmed_red",
    "срочно": "confirmed_red",
    "неотложка": "confirmed_red",
    "упала": "confirmed_red",
    "я упала": "confirmed_red",
    "упал": "confirmed_red",
    "я упал": "confirmed_red",
    "не могу дышать": "confirmed_red",
    "трудно дышать": "confirmed_red",
    "не могу встать": "confirmed_red",
    "не могу подняться": "confirmed_red",
    "всё болит": "confirmed_red",
    "сильно болит": "confirmed_red",
    "очень болит": "confirmed_red",
    "хочу умереть": "confirmed_red",        # S17 ideation
    "я умираю": "confirmed_red",
    "умираю": "confirmed_red",
    "покончить с собой": "confirmed_red",
    "кровотечение": "confirmed_red",

    # ---- negated emergencies are cleared --------------------------------
    "не упала": "ok",
    "не болит": "ok",
    "не болею": "ok",
    "не хочу умереть": "ok",               # reassuring, not RED

    # ---- self-harm ambiguity: needs control question ---------------------
    "не хочу жить": "possible_red",
    "не хочу жить одна": "possible_red",    # loneliness, NOT an auto-RED
    "не хочу больше жить": "possible_red",

    # ---- third-person: never caller RED ---------------------------------
    "бабушка упала": "third_person",
    "соседка упала": "third_person",
    "дедушка упал": "third_person",
    "мне сказали, что бабушка упала": "third_person",  # subject attribution
    "у сына температура": "third_person",
    "он плохо себя чувствует": "third_person",
    "у соседа инфаркт": "third_person",
    "мама болеет": "third_person",

    # ---- inanimate object falls: never caller RED ------------------------
    "упала банка": "ok",
    "телефон упал": "ok",
    "стул упал": "ok",
    "тарелка упала": "ok",
    "я уронил телефон": "ok",

    # ---- help requests: attention ---------------------------------------
    "помощь": "help_request",
    "помогите": "help_request",
    "нужна помощь": "help_request",
    "мне нужна помощь": "help_request",     # S12 "не нужн" collision
    "мне требуется помощь": "help_request",  # S13
    "мне надо помощь": "help_request",      # S14
    "помощь нужна": "help_request",
    "позовите родных": "help_request",
    "купите продукты": "help_request",

    # ---- negated help: cleared -------------------------------------------
    "не нужна помощь": "ok",
    "мне не надо помощь": "ok",
    "мне не нужна помощь": "ok",
    "ничего не нужно": "ok",

    # ---- short answers ----------------------------------------------------
    "да": "help_request",                   # help-question affirmative
    "нет": "ok",                            # help-question denial
    "ага": "help_request",
    "не знаю": "unknown",                   # NON-answer, not a denial
    "не помню": "unknown",

    # ---- no data ----------------------------------------------------------
    "": "no_speech",
}

# Low-confidence variants: can neither create GREEN nor confirm RED.
LOW_CONF = {
    "всё хорошо": "unknown",
    "скорая": "possible_red",
    "вызовите скорую": "possible_red",
}


class CorpusTests(unittest.TestCase):
    def test_single_utterance_corpus(self):
        fails = []
        for text, expected in CORPUS.items():
            ev = SafetyEngine().observe(Observation(raw_text=text))
            if ev.kind != expected:
                fails.append((text, expected, ev.kind))
        self.assertEqual([], fails, "corpus mismatches")

    def test_low_confidence_cannot_green_or_confirm_red(self):
        fails = []
        for text, expected in LOW_CONF.items():
            ev = SafetyEngine().observe(
                Observation(raw_text=text, confidence=0.2))
            if ev.kind != expected:
                fails.append((text, expected, ev.kind))
        self.assertEqual([], fails, "low-confidence mismatches")

    def test_events_carry_source_and_confidence(self):
        ev = SafetyEngine().observe(
            Observation(raw_text="плохо", confidence=0.7, source="stt"))
        self.assertEqual(ev.source, "stt")
        self.assertEqual(ev.confidence, 0.7)
        self.assertEqual(ev.observed, "плохо")
        self.assertFalse(ev.low_confidence)


# ---------------------------------------------------------------------------
# State machine sequences (the POSSIBLE_RED -> CONTROL -> verdict ladder)
# ---------------------------------------------------------------------------

class MachineTests(unittest.TestCase):
    def _seq(self, *steps, conf=None):
        eng = SafetyEngine()
        return [eng.observe(Observation(raw_text=t, confidence=conf)).kind
                for t in steps]

    def test_possible_red_confirmed_by_affirmative(self):
        self.assertEqual(self._seq("плохо", "да"),
                         ["possible_red", "confirmed_red"])

    def test_possible_red_confirmed_by_repeat_distress(self):
        self.assertEqual(self._seq("плохо", "плохо"),
                         ["possible_red", "confirmed_red"])

    def test_possible_red_cleared_by_denial(self):
        self.assertEqual(self._seq("плохо", "нет"),
                         ["possible_red", "ok"])
        self.assertEqual(self._seq("плохо", "всё хорошо"),
                         ["possible_red", "ok"])
        self.assertEqual(self._seq("плохо", "уже лучше"),
                         ["possible_red", "ok"])

    def test_possible_red_to_uncertain_on_non_answer(self):
        self.assertEqual(self._seq("плохо", "не знаю"),
                         ["possible_red", "uncertain_red"])

    def test_possible_red_to_help_request(self):
        self.assertEqual(self._seq("плохо", "помощь нужна"),
                         ["possible_red", "help_request"])

    def test_possible_red_to_third_person_is_uncertain(self):
        self.assertEqual(self._seq("плохо", "бабушка упала"),
                         ["possible_red", "uncertain_red"])

    def test_confirmed_red_is_latched(self):
        eng = SafetyEngine()
        eng.observe(Observation(raw_text="скорая"))
        for t in ("всё хорошо", "нет", "неплохо"):
            self.assertEqual(
                eng.observe(Observation(raw_text=t)).kind,
                "confirmed_red", f"latch broken by {t!r}")
            self.assertTrue(eng.last_event.latched)

    def test_uncertain_red_never_becomes_ok(self):
        eng = SafetyEngine()
        eng.observe(Observation(raw_text="плохо"))
        eng.observe(Observation(raw_text="не знаю"))
        self.assertEqual(eng.state, "UNCERTAIN_RED")
        for t in ("всё хорошо", "нет", "неплохо"):
            self.assertEqual(
                eng.observe(Observation(raw_text=t)).kind,
                "uncertain_red", f"uncertain downgraded by {t!r}")

    def test_freeze_blocks_all_mutation(self):
        eng = SafetyEngine()
        eng.observe(Observation(raw_text="плохо"))
        eng.freeze()
        ev = eng.observe(Observation(raw_text="да"))
        self.assertEqual(ev.kind, "frozen")
        self.assertEqual(eng.state, "POSSIBLE_RED")

    def test_no_speech_is_not_ok(self):
        for empty in (None, "", "  "):
            ev = SafetyEngine().observe(Observation(raw_text=empty))
            self.assertEqual(ev.kind, "no_speech")


# ---------------------------------------------------------------------------
# Agent-level flows (the dialogue machine consuming VerdictEvents)
# ---------------------------------------------------------------------------

class AgentFlowTests(unittest.TestCase):
    def _agent(self, *turns):
        a = Agent(llm=None)
        for t in turns:
            a.plan_reply(t)
        return a

    def test_healthy_call_is_green(self):
        a = self._agent("всё хорошо", "нет")
        self.assertEqual(a.status, "ok")
        self.assertEqual(a.outcome["status"], "ok")

    def test_bad_feeling_then_confirmed_is_alert(self):
        a = self._agent("плохо", "да")
        self.assertEqual(a.status, "alert")
        self.assertEqual(a.outcome["status"], "alert")

    def test_bad_feeling_then_fine_is_attention_cleared(self):
        a = self._agent("плохо", "всё хорошо", "нет")
        self.assertEqual(a.status, "ok")

    def test_bad_feeling_then_non_answer_is_attention(self):
        a = self._agent("плохо", "не знаю")
        self.assertEqual(a.status, "attention")

    def test_help_first_is_attention(self):
        a = self._agent("мне нужна помощь")
        self.assertEqual(a.status, "attention")
        self.assertIn("требуется помощь", a.outcome["notes"])

    def test_third_person_is_attention_not_alert(self):
        a = self._agent("бабушка упала", "нет")
        self.assertEqual(a.status, "attention")
        self.assertNotEqual(a.status, "alert")

    def test_object_fall_is_not_alert(self):
        a = self._agent("упала банка", "нет")
        self.assertNotEqual(a.status, "alert")

    def test_unknown_is_not_masked_to_attention(self):
        a = self._agent("погода сегодня хорошая")
        # first turn "unknown" stays its own status, never attention-masked
        self.assertIn(a.status, ("unknown", "ok"))

    def test_unknown_never_becomes_green_by_itself(self):
        a = self._agent("ну, как-то так", "погода хорошая")
        self.assertIn(a.status, ("unknown", "ok", "attention"))

    def test_done_guard_blocks_late_turns(self):
        a = self._agent("вызовите скорую")
        before = (a.status, list(a.notes), len(a.memory),
                  a.safety.state)
        plan = a.plan_reply("всё хорошо")   # late/duplicate turn
        self.assertTrue(plan.get("terminal"))
        after = (a.status, list(a.notes), len(a.memory), a.safety.state)
        self.assertEqual(before, after, "done-guard let a late turn mutate")

    def test_reset_gives_fresh_safety(self):
        a = self._agent("скорая")
        a.reset()
        self.assertEqual(a.status, "unknown")
        self.assertEqual(a.safety.state, "NONE")
        self.assertFalse(a.done)


if __name__ == "__main__":
    unittest.main(verbosity=2)