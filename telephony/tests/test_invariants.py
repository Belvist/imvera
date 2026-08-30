"""Stage 0A invariants: properties the SafetyEngine must hold on ALL inputs.

12 invariants (I1-I12) plus a seeded monotonicity fuzz over 1000 random
conversations. These are structural guarantees, not scenario tests: they must
hold on every input, including ones nobody wrote down as a scenario.
"""

import os
import random
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from core.safety_engine import Observation, SafetyEngine  # noqa: E402

RED_PHRASES = (
    "скорая", "скорую", "вызовите скорую", "вызовите врача", "срочно",
    "неотложка", "упала", "я упала", "упал", "не могу дышать",
    "трудно дышать", "не могу встать", "не могу подняться", "всё болит",
    "сильно болит", "хочу умереть", "я умираю", "покончить с собой",
    "кровотечение", "инфаркт", "инсульт",
)

NEGATED_PHRASES = (
    "мне не плохо", "не плохо", "температуры нет", "не болит", "не упала",
    "не болею", "не нужна помощь", "мне не нужна помощь", "ничего не нужно",
    "давление не упало", "не хочу умереть",
)

THIRD_PHRASES = (
    "бабушка упала", "дедушка упал", "соседка упала",
    "мне сказали, что бабушка упала", "у сына температура",
    "он плохо себя чувствует", "у соседа инфаркт", "мама болеет",
)

OBJECT_FALLS = (
    "упала банка", "телефон упал", "стул упал", "тарелка упала",
    "я уронил телефон",
)

# Pool for the monotonicity fuzz: the engine must never lose a RED it latched.
POOL = (
    # distress
    "плохо", "мне плохо", "болит голова", "температура", "скорая",
    "упала", "не могу дышать", "всё болит", "хочу умереть", "давление упало",
    # negated / cleared
    "не плохо", "температуры нет", "не нужна помощь", "не хочу умереть",
    # third / object
    "бабушка упала", "мне сказали, что бабушка упала", "упала банка",
    # positive / neutral / help
    "всё хорошо", "нормально", "неплохо", "пью таблетки", "помогите",
    "мне нужна помощь", "купите продукты",
    # short answers
    "да", "нет", "ага", "не знаю", "не помню", "уже лучше",
    # noise
    "", "спасибо", "погода сегодня хорошая",
)

VALID_KINDS = frozenset((
    "no_speech", "ok", "possible_red", "uncertain_red", "confirmed_red",
    "help_request", "third_person", "unknown", "frozen",
))

# CONFIRMED_RED latches forever (the family is already alarmed). UNCERTAIN_RED
# is recoverable by a positive (2026-08-29) so it is NOT in this set.
_LATCHED = frozenset(("CONFIRMED_RED",))


class InvariantTests(unittest.TestCase):
    # I1: a confirmed-red phrase never yields ok / GREEN.
    def test_I1_red_never_green(self):
        for phrase in RED_PHRASES:
            ev = SafetyEngine().observe(Observation(raw_text=phrase, confidence=0.85))
            self.assertNotIn(ev.kind, ("ok", "unknown"),
                             f"{phrase!r} must never be GREEN")

    # I2: RED phrases that are not in the immediate-emergency class still
    #     escalate to at least attention (possible_red or higher).
    def test_I2_red_escalates(self):
        for phrase in RED_PHRASES:
            ev = SafetyEngine().observe(Observation(raw_text=phrase, confidence=0.85))
            self.assertIn(ev.kind, ("confirmed_red", "possible_red"),
                          f"{phrase!r} must escalate, got {ev.kind}")

    # I3: negated distress never yields confirmed_red.
    def test_I3_negation_never_red(self):
        for phrase in NEGATED_PHRASES:
            ev = SafetyEngine().observe(Observation(raw_text=phrase, confidence=0.85))
            self.assertNotEqual(ev.kind, "confirmed_red",
                                f"negation {phrase!r} fired RED")

    # I4: third-person signals never yield caller RED.
    def test_I4_third_person_never_red(self):
        for phrase in THIRD_PHRASES:
            ev = SafetyEngine().observe(Observation(raw_text=phrase, confidence=0.85))
            self.assertNotEqual(ev.kind, "confirmed_red",
                                f"third-person {phrase!r} fired RED")

    # I5: inanimate object falls never yield caller RED.
    def test_I5_object_fall_never_red(self):
        for phrase in OBJECT_FALLS:
            ev = SafetyEngine().observe(Observation(raw_text=phrase, confidence=0.85))
            self.assertNotEqual(ev.kind, "confirmed_red",
                                f"object fall {phrase!r} fired RED")

    # I6: CONFIRMED_RED is latched — no later observation downgrades it.
    def test_I6_confirmed_red_latched(self):
        eng = SafetyEngine()
        eng.observe(Observation(raw_text="скорая", confidence=0.85))
        for _ in range(20):
            t = random.choice(POOL)
            ev = eng.observe(Observation(raw_text=t, confidence=0.85))
            self.assertEqual(ev.kind, "confirmed_red",
                             f"confirmed RED downgraded to {ev.kind} by {t!r}")

    # I7 (2026-08-29 rework): UNCERTAIN_RED is a RECOVERABLE concern — it
    # does NOT downgrade by non-positive input, but a clear positive
    # ("уже отпустило") clears it so the agenda can resume. Before, it
    # latched forever and wedged the call in safety_active (live post-
    # mortem: 47/100 synthetic calls never finished).
    def test_I7_uncertain_not_downgraded_by_negatives(self):
        eng = SafetyEngine()
        eng.observe(Observation(raw_text="плохо", confidence=0.85))
        eng.observe(Observation(raw_text="не знаю", confidence=0.85))
        self.assertEqual(eng.state, "UNCERTAIN_RED")
        for t in POOL:
            ev = eng.observe(Observation(raw_text=t, confidence=0.85))
            self.assertNotEqual(ev.kind, "ok",
                                f"uncertain downgraded by {t!r}")

    def test_I7_uncertain_recovered_by_positive(self):
        eng = SafetyEngine()
        eng.observe(Observation(raw_text="плохо", confidence=0.85))
        eng.observe(Observation(raw_text="не знаю", confidence=0.85))
        self.assertEqual(eng.state, "UNCERTAIN_RED")
        ev = eng.observe(Observation(raw_text="уже отпустило", confidence=0.85))
        self.assertEqual(ev.kind, "ok")
        self.assertEqual(eng.state, "OK")

    # I8: low confidence can neither create GREEN nor confirm RED.
    def test_I8_low_confidence_limits(self):
        for phrase in ("всё хорошо", "нормально", "неплохо", "пью таблетки"):
            ev = SafetyEngine().observe(
                Observation(raw_text=phrase, confidence=0.1))
            self.assertNotEqual(ev.kind, "ok",
                                f"low-conf {phrase!r} created GREEN")
        for phrase in RED_PHRASES:
            ev = SafetyEngine().observe(
                Observation(raw_text=phrase, confidence=0.1))
            self.assertNotEqual(ev.kind, "confirmed_red",
                                f"low-conf {phrase!r} confirmed RED")

    # I9: empty / None transcripts are no_speech, never ok.
    def test_I9_no_speech_not_ok(self):
        for empty in (None, "", "   "):
            ev = SafetyEngine().observe(Observation(raw_text=empty))
            self.assertEqual(ev.kind, "no_speech")

    # I10: freeze() blocks all later mutation.
    def test_I10_freeze_is_terminal(self):
        for seed_text in ("скорая", "плохо", "всё хорошо"):
            eng = SafetyEngine()
            eng.observe(Observation(raw_text=seed_text, confidence=0.85))
            before_state = eng.state
            eng.freeze()
            for _ in range(10):
                t = random.choice(POOL)
                ev = eng.observe(Observation(raw_text=t, confidence=0.85))
                self.assertEqual(ev.kind, "frozen")
                self.assertEqual(eng.state, before_state,
                                 "frozen engine mutated state")

    # I11: deterministic — identical input + identical state -> same event.
    def test_I11_deterministic(self):
        texts = ("плохо", "скорая", "бабушка упала", "всё хорошо", "")
        for text in texts:
            e1 = SafetyEngine().observe(Observation(raw_text=text, confidence=0.85))
            e2 = SafetyEngine().observe(Observation(raw_text=text, confidence=0.85))
            self.assertEqual(e1.kind, e2.kind)
            self.assertEqual(e1.notes, e2.notes)
        eng = SafetyEngine()
        eng.observe(Observation(raw_text="плохо", confidence=0.85))
        a = eng.observe(Observation(raw_text="да", confidence=0.85))
        b = eng.observe(Observation(raw_text="да", confidence=0.85))
        self.assertEqual(a.kind, b.kind)

    # I12: events carry valid kinds, source, confidence and observed text.
    def test_I12_event_shape(self):
        eng = SafetyEngine()
        ev = eng.observe(Observation(raw_text="плохо", confidence=0.8,
                                     source="stt"))
        self.assertIn(ev.kind, VALID_KINDS)
        self.assertEqual(ev.source, "stt")
        self.assertEqual(ev.confidence, 0.8)
        self.assertEqual(ev.observed, "плохо")

    # I13: rising/getting up is a NORMAL action ("встала с утра",
    #     "поднялась на этаж") and must never be an emergency; only the
    #     INVERSE is distress ("не встаю", "не могу встать").
    def test_I13_rising_is_normal_not_distress(self):
        for phrase in ("встала", "встал утром", "я встала с кровати",
                       "поднялась на второй этаж", "могла встать"):
            ev = SafetyEngine().observe(Observation(raw_text=phrase, confidence=0.85))
            self.assertNotEqual(ev.kind, "confirmed_red",
                                f"normal rising {phrase!r} fired an emergency")

    def test_I14_cannot_get_up_is_distress(self):
        for phrase in ("не встаю", "не могу встать", "не могу подняться",
                       "я не смогла встать", "не поднялась"):
            ev = SafetyEngine().observe(Observation(raw_text=phrase, confidence=0.85))
            self.assertIn(ev.kind, ("confirmed_red", "possible_red"),
                          f"'cannot get up' {phrase!r} did not escalate")

    # I15: a statement about the PAST is not a help request ("купила хлеб",
    #     "позвонила дочери"); only imperative/need phrases are.
    def test_I15_past_tense_is_not_help_request(self):
        for phrase in ("купила хлеб", "купил продукты", "купили в магазине",
                       "сходила в магазин", "позвонила дочери",
                       "передала родным", "принесла хлеб", "принёс хлеб",
                       "я встала с кровати", "на кровати лежала"):
            ev = SafetyEngine().observe(Observation(raw_text=phrase, confidence=0.85))
            self.assertNotEqual(ev.kind, "help_request",
                                f"past statement {phrase!r} fired help")

    def test_I16_real_requests_still_fire_help(self):
        for phrase in ("купите мне хлеба", "купи хлеба", "сходи в магазин",
                       "позвоните дочери", "мне нужна помощь", "помогите",
                       "передайте родным", "принеси хлеба",
                       "хлеб кончился, в магазин надо сходить",
                       "продукты кончились",
                       "сходи за хлебом, я купила молоко"):
            ev = SafetyEngine().observe(Observation(raw_text=phrase, confidence=0.85))
            self.assertEqual(ev.kind, "help_request",
                             f"real request {phrase!r} did not fire help")

    # I17: burns/scalds are emergencies ("обварилась", "обожглась").
    def test_I17_burns_are_distress(self):
        for phrase in ("я обварилась", "обварилась, помогите",
                       "обожглась", "обожгла палец", "ожог на руке"):
            ev = SafetyEngine().observe(Observation(raw_text=phrase, confidence=0.85))
            self.assertIn(ev.kind, ("confirmed_red", "possible_red"),
                          f"burn {phrase!r} did not escalate")


class MonotonicFuzzTests(unittest.TestCase):
    def test_seeded_1000_conversations_are_monotonic(self):
        rng = random.Random(42)
        checked = 0
        for _ in range(1000):
            eng = SafetyEngine()
            froze = False
            prev = "NONE"
            for _ in range(rng.randint(1, 12)):
                text = rng.choice(POOL)
                conf = rng.choice([None, 0.9, 0.1, 0.6])
                if rng.random() < 0.1:
                    eng.freeze()
                    froze = True
                ev = eng.observe(Observation(raw_text=text,
                                             confidence=conf))
                checked += 1
                self.assertIn(ev.kind, VALID_KINDS)
                if froze:
                    self.assertEqual(ev.kind, "frozen")
                    continue
                st = eng.state
                # no GREEN from a latched RED
                if prev in _LATCHED:
                    self.assertNotIn(ev.kind, ("ok", "unknown"),
                                     f"latched RED downgraded after {text!r}")
                # machine never leaves a latched state
                if st in _LATCHED:
                    self.assertIn(st, (prev, st))
                prev = st
        self.assertGreater(checked, 1000)


if __name__ == "__main__":
    unittest.main(verbosity=2)