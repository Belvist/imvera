"""2026-08-29 dialogue regressions (FIXES_PLAN P1):
  * help confirmation: a bare «да» right after a help question must be
    recorded as help, not bounced into a generic ack (the _help_pending flag
    was cleared in plan_reply before _plan_mode could consume it);
  * closing loop: a second short goodbye after the confirmation question is
    the confirmation itself — no infinite re-asking (the flag was never set);
  * agenda bounds: reaching the agenda-question helper with the agenda
    exhausted used to raise IndexError and drop the turn.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dialogue import Agent  # noqa: E402


def _run(a, *texts):
    """Drive an agent through a script, returning (final_plan, agent)."""
    p = None
    for t in texts:
        p = a.plan_reply(t)
    return p, a


class HelpConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.agent = Agent(llm=None)

    def test_help_question_da_is_recorded(self):
        """«да» on «Нужна ли вам помощь?» records the help request."""
        a = self.agent
        # First put the help question on the table.
        p = a.plan_reply("мне нужна помощь")
        self.assertNotEqual(p.get("intent"), None)  # help flow started
        # Now the caller confirms with a bare «да».
        p2 = a.plan_reply("да")
        # The confirmation must land in the help branch: Vera asks what is
        # needed / says it is recorded — NOT a generic acknowledgement.
        self.assertIn("требуется помощь", a.notes)
        fb = (p2.get("fallback") or "").lower()
        self.assertTrue(
            any(w in fb for w in ("помощ", "запис", "нужн", "близк", "сделать")),
            f"help confirmation got: {fb!r}")

    def test_help_then_details_recorded(self):
        """After the confirmation, a details reply stays in the help flow —
        the flag is re-armed for the «что именно нужно?» follow-up, not
        consumed into a dead generic ack."""
        a = self.agent
        a.plan_reply("мне нужна помощь")
        a.plan_reply("да")
        self.assertIn("требуется помощь", a.notes)
        p = a.plan_reply("принесите воды")
        fb = (p.get("fallback") or "").lower()
        self.assertTrue(
            any(w in fb for w in ("помощ", "запис", "сделать", "родн",
                                  "воды", "близк")),
            f"help follow-up got: {fb!r}")


class ClosingLoopTests(unittest.TestCase):
    def setUp(self):
        self.agent = Agent(llm=None)
        self.agent.start_check_in()

    def test_repeat_goodbye_finishes_not_reasks(self):
        a = self.agent
        p1 = a.plan_reply("всё хорошо")     # close topic 0 -> topic on table
        # Short goodbye during check-in: confirm once.
        p2 = a.plan_reply("до свидания")
        self.assertIn("прощаетесь", (p2.get("fallback") or ""))
        self.assertFalse(p2.get("terminal"))
        # A second short goodbye IS the confirmation -> terminal.
        p3 = a.plan_reply("до свидания")
        self.assertTrue(p3.get("terminal"), "second goodbye must finish")
        self.assertEqual(a.mode, "closing")

    def test_goodbye_then_continue_resets_confirmation(self):
        a = self.agent
        a.plan_reply("всё хорошо")
        a.plan_reply("до свидания")         # asks to confirm
        p = a.plan_reply("нет, я ещё не прощаюсь, расскажу про сон")
        self.assertFalse(p.get("terminal"))
        # A later real goodbye gets its own single confirmation again.
        p2 = a.plan_reply("до свидания")
        self.assertIn("прощаетесь", (p2.get("fallback") or ""))
        self.assertFalse(p2.get("terminal"))


class AgendaBoundsTests(unittest.TestCase):
    def setUp(self):
        self.agent = Agent(llm=None)
        self.agent.start_check_in()

    def test_no_index_error_after_agenda_finished(self):
        a = self.agent
        # Walk the whole 5-topic agenda to the end.
        a.plan_reply("да, всё хорошо")
        a.plan_reply("настроение хорошее")
        a.plan_reply("спала хорошо")
        a.plan_reply("буду читать")
        a.plan_reply("да, запишите родным")
        # Agenda exhausted; any further non-question turn used to raise
        # IndexError inside _agenda_question (interrupt-resume path).
        p = a.plan_reply("спасибо")
        self.assertIsInstance(p, dict)
        self.assertFalse(p.get("terminal"))

    def test_story_after_agenda_with_family_question_ok(self):
        a = self.agent
        a.set_family_questions([{"author": "Мария", "text": "Как ваши ноги?"}])
        a.plan_reply("да, всё хорошо")
        a.plan_reply("настроение хорошее")
        a.plan_reply("спала хорошо")
        a.plan_reply("буду читать")
        a.plan_reply("да, запишите родным")
        # 4-5 word story with a family question attached used to hit the
        # same IndexError on the exhausted agenda.
        p = a.plan_reply("внучка приходила вчера")
        self.assertIsInstance(p, dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)