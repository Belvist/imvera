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
        self.assertTrue("план" in p["fallback"].lower()
                        or "займётесь" in p["fallback"].lower())
        p = a.plan_reply("всё хорошо, буду ещё читать")
        fb = p["fallback"].lower()
        self.assertTrue(any(w in fb for w in
                            ("родн", "передать", "записать")))
        p = a.plan_reply("хорошо, запишите для них пару слов")
        self.assertIn("записала", p["fallback"].lower())
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
