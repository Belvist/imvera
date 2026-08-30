"""Family app <-> call pipeline (2026-08-23): offline coverage.

Covers key/phone/text helpers and the dialogue integration: family-app
questions become dynamic agenda entries AFTER the standard wellness topics,
the exact question text reaches the elder, answers are snapshotted onto the
question and the verdict notes mention the delivery."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dialogue import Agent  # noqa: E402
from core.family import (FamilyValidationError, hash_key, new_key,  # noqa: E402
                         normalize_phone, validate_question_text)


class FamilyUtilsTests(unittest.TestCase):
    def test_new_key_shape_and_hash_stability(self):
        k = new_key()
        self.assertTrue(k.startswith("mv_"))
        self.assertGreater(len(k), 20)
        h1, h2 = hash_key(k), hash_key(k)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)          # sha256 hex
        self.assertNotEqual(hash_key(k), hash_key(k + "x"))

    def test_normalize_phone(self):
        self.assertEqual(normalize_phone("+7 (900) 123-45-67"),
                         "79001234567")
        # 8-code and 7-code forms are the SAME number (RU trunk prefix)
        self.assertEqual(normalize_phone("8-900-123-45-67"), "79001234567")
        self.assertEqual(normalize_phone("79001234567"), "79001234567")
        self.assertEqual(normalize_phone(None), "")
        self.assertEqual(normalize_phone(""), "")

    def test_validate_question_text(self):
        self.assertEqual(validate_question_text("  приняла ли таблетки? "),
                         "приняла ли таблетки?")
        with self.assertRaises(FamilyValidationError):
            validate_question_text("")
        with self.assertRaises(FamilyValidationError):
            validate_question_text("  ")
        with self.assertRaises(FamilyValidationError):
            validate_question_text("х" * 501)


class FamilyAgendaTests(unittest.TestCase):
    """The call walks 5 standard topics, then delivers family questions."""

    def _reply(self, a, text, conf=0.85, reason=None):
        # Qwen3 honest: None -> low (U9). Legacy agenda tests expect high
        # confidence to advance topics; set explicitly so default None
        # (fail-safe) does not mask missing observe_confidence in tests.
        a.observe_confidence(conf)
        return a.plan_reply(text, reason=reason)

    def _agent_with_questions(self):
        a = Agent(llm=None)
        a.set_family_questions([
            {"id": "q1", "text": "Приняла ли ты таблетки сегодня?",
             "author": "дочь"},
            {"id": "", "text": "   ", "author": "сын"},   # skipped silently
        ])
        a.start_check_in()
        return a

    def test_family_question_asked_verbatim_after_standard_topics(self):
        a = self._agent_with_questions()
        # Walk the 5 standard topics exactly like test_task_agenda does.
        p = self._reply(a, "да, всё хорошо")                 # -> настроение
        self.assertIn("настроение", p["fallback"].lower())
        p = self._reply(a, "настроение хорошее, спасибо")    # -> сон
        self.assertTrue("сон" in p["fallback"].lower()
                        or "спал" in p["fallback"].lower())
        p = self._reply(a, "спала хорошо")                   # -> планы
        p = self._reply(a, "всё хорошо, буду ещё читать")    # -> передать родн.
        p = self._reply(a, "хорошо, запишите для них пару слов")
        # NOW the family question is on the table — VERBATIM.
        fb = p["fallback"]
        self.assertIn("Вопрос от родных (дочь)", fb)
        self.assertIn("Приняла ли ты таблетки сегодня?", fb)
        # the LLM goal carries the exact text too (free wording stays on-task)
        self.assertIn("Приняла ли ты таблетки сегодня?", p.get("intent") or "")
        self.assertEqual(a._agenda_topic(), "вопрос от родных")
        # only ONE pending item survived (the blank one is dropped)
        self.assertEqual(len(a.family_questions), 1)

    def test_answer_is_snapshotted_then_wrap_up(self):
        a = self._agent_with_questions()
        for phrase in ("да, всё хорошо", "настроение хорошее, спасибо",
                       "спала хорошо", "всё хорошо, буду ещё читать",
                       "хорошо, запишите для них пару слов"):
            self._reply(a, phrase)
        answer = "всё хорошо, буду ещё читать"
        p = self._reply(a, answer)
        q = a.family_questions[0]
        self.assertEqual(q["status"], "asked")
        self.assertEqual(q["answer"], answer)
        self.assertTrue(any("вопрос родных" in n for n in a.notes))
        # the agenda just FINISHED -> wrap-up in the very same reply
        self.assertTrue(any(w in p["fallback"].lower() for w in
                            ("записа", "доба")))

    def test_unanswered_question_stays_pending(self):
        a = self._agent_with_questions()
        for phrase in ("да, всё хорошо", "настроение хорошее, спасибо",
                       "спала хорошо", "всё хорошо, буду ещё читать"):
            self._reply(a, phrase)
        self.assertEqual(a.family_questions[0]["status"], "pending")

    def test_no_questions_keeps_base_agenda(self):
        a = Agent(llm=None)
        a.start_check_in()
        p = self._reply(a, "да, всё хорошо")
        self.assertIn("настроение", p["fallback"].lower())
        p = self._reply(a, "нормально")
        p = self._reply(a, "нормально")
        p = self._reply(a, "нормально")
        p = self._reply(a, "нормально")
        # fifth topic closed -> straight to wrap-up, no family entries
        self.assertTrue(any(w in p["fallback"].lower() for w in
                            ("записа", "доба")))
        self.assertEqual(a.family_questions, [])
        self.assertEqual(a._agenda_extra, ())


if __name__ == "__main__":
    unittest.main(verbosity=2)
