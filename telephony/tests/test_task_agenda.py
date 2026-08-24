"""Task-oriented call agenda (2026-08-23): Vera drives the call through a
soft topic checklist instead of random-walking topics like a chat bot.

Covers: agenda order, per-topic verdict notes, safety interjection pause +
resume, and the wrap-up after the last topic."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dialogue import Agent  # noqa: E402


class TaskAgendaTests(unittest.TestCase):
    def setUp(self):
        self.agent = Agent(llm=None)
        self.agent.start_check_in()

    def test_agenda_walks_in_order_and_notes_topics(self):
        a = self.agent
        # greeting = topic 0 on the table -> a short OK closes it and asks
        # the NEXT topic («настроение»), instantly, no LLM.
        p = a.plan_reply("да, всё хорошо")
        self.assertIn("настроение", p["fallback"].lower())
        p = a.plan_reply("настроение хорошее, спасибо")
        self.assertTrue("сон" in p["fallback"].lower()
                        or "спал" in p["fallback"].lower())
        p = a.plan_reply("спала хорошо")
        self.assertTrue(any(w in p["fallback"].lower() for w in
                            ("план", "займётес", "делать", "проведёте")))
        p = a.plan_reply("всё хорошо, буду ещё читать")
        fb = p["fallback"].lower()
        self.assertTrue(any(w in fb for w in
                            ("родн", "передать", "записать")))
        p = a.plan_reply("хорошо, запишите для них пару слов")
        self.assertIn("записа", p["fallback"].lower())
        for topic in ("самочувствие", "настроение", "сон", "планы",
                      "передать родным"):
            self.assertIn(f"обсуждено: {topic}", a.notes)

    def test_safety_interjection_pauses_then_resumes(self):
        a = self.agent
        p = a.plan_reply("да, всё хорошо")          # closes самочувствие
        self.assertIn("настроение", p["fallback"].lower())
        # symptom mid-agenda: safety control question PAUSES the agenda
        p = a.plan_reply("голова болит и кружится")
        self.assertTrue("плохо" in p["fallback"].lower()
                        or "нехорошо" in p["fallback"].lower())
        # denial clears the concern (its own scripted follow-up)
        p = a.plan_reply("нет, не сейчас хорошо, отпустило")
        self.assertTrue("перестраховалась" in p["fallback"].lower()
                        or "извините за тревогу" in p["fallback"].lower())
        # next short OK RESUMES the agenda where it paused — now «сон»,
        # NOT a restart from «самочувствие»
        p = a.plan_reply("да, всё хорошо")
        self.assertTrue("сон" in p["fallback"].lower()
                        or "спал" in p["fallback"].lower())

    def test_empty_turns_do_not_advance_agenda(self):
        a = self.agent
        for _ in range(3):
            a.plan_reply("")
        self.assertEqual(a._agenda_idx, 0)
        p = a.plan_reply("да, всё хорошо")
        self.assertIn("настроение", p["fallback"].lower())


class VarietyTests(unittest.TestCase):
    """Cross-call variety (2026-08-23): canned questions must NOT repeat
    between consecutive calls in the same process."""

    @staticmethod
    def _run_call():
        a = Agent(llm=None)
        a.start_check_in()
        asked = []
        asked.append(a.plan_reply("да, всё хорошо")["fallback"])    # mood
        asked.append(a.plan_reply("настроение хорошее")["fallback"])  # sleep
        asked.append(a.plan_reply("спала хорошо")["fallback"])      # plans
        asked.append(a.plan_reply("всё хорошо, буду читать")["fallback"])
        return asked

    def test_two_calls_no_repeated_canned_questions(self):
        first = self._run_call()
        second = self._run_call()
        overlap = set(first) & set(second)
        self.assertFalse(overlap,
                         f"canned lines repeated across calls: {overlap}")

    def test_small_pool_degrades_gracefully(self):
        a = Agent(llm=None)
        pool = ["А?", "Б?"]
        for _ in range(10):
            pick = a._pick_not_repeated(pool)
            self.assertIn(pick, pool)

    def test_goodbye_pool_variety_and_no_promises(self):
        # 2026-08-24: the close used to be 2 phrases heard on EVERY call.
        # Product rules: Vera never promises to call/send anything — she
        # only records; at most ONE question mark per line; unique lines.
        self.assertGreaterEqual(len(Agent.GOODBYES), 5)
        self.assertEqual(len(set(Agent.GOODBYES)), len(Agent.GOODBYES))
        forbidden = ("вызову", "позвоню", "отправлю", "предупрежу",
                     "передам", "сообщу")
        for line in Agent.GOODBYES:
            low = line.lower()
            for word in forbidden:
                self.assertNotIn(word, low, f"promise in goodbye: {line}")
            self.assertLessEqual(line.count("?"), 1)
            self.assertNotIn(" ты ", f" {low} ")

    def test_generic_acks_pool_variety_and_no_promises(self):
        # 2026-08-24: generic acknowledgments were THREE bare phrases
        # («Понимаю.», «Вот как.») picked by plain random.choice — the exact
        # empty nods the system prompt forbids. Pool must be warm, unique,
        # promise-free and rotate via _pick_not_repeated.
        pool = Agent.GENERIC_ACKS
        self.assertGreaterEqual(len(pool), 5)
        self.assertEqual(len(set(pool)), len(pool))
        forbidden = ("вызову", "позвоню", "отправлю", "предупрежу",
                     "передам", "сообщу")
        for line in pool:
            low = line.lower()
            for word in forbidden:
                self.assertNotIn(word, low, f"promise in ack: {line}")
            self.assertLessEqual(line.count("?"), 1)
            self.assertNotIn(" ты ", f" {low} ")
        # rotation actually varies picks within one call (no bare repeats):
        a = Agent(llm=None)
        picks = {a._pick_not_repeated(pool) for _ in range(4)}
        self.assertGreaterEqual(len(picks), 3)

    def test_small_pools_variety_and_no_promises(self):
        # 2026-08-24: silence escalation / false-alarm apology / third-person
        # worry follow-ups each had 2-4 inline lines; now named class pools
        # (>= 4 unique, promise-free, «вы», <=1 question mark) that rotate
        # via _pick_not_repeated.
        forbidden = ("вызову", "позвоню", "отправлю", "предупрежу",
                     "передам", "сообщу")
        for pool in (Agent.SILENCE_ESCALATION, Agent.FALSE_ALARM_ACKS,
                     Agent.WORRY_FOLLOWUPS):
            self.assertGreaterEqual(len(pool), 4)
            self.assertEqual(len(set(pool)), len(pool))
            for line in pool:
                low = line.lower()
                for word in forbidden:
                    self.assertNotIn(word, low,
                                     f"promise in line: {line}")
                self.assertNotIn(" ты ", f" {low} ")
                self.assertLessEqual(line.count("?"), 1)
        a = Agent(llm=None)
        picks = {a._pick_not_repeated(Agent.SILENCE_ESCALATION)
                 for _ in range(5)}
        self.assertGreaterEqual(len(picks), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
