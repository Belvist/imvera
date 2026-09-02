"""2026-08-29 dialogue regressions (FIXES_PLAN P1):
  * help confirmation: a bare «да» right after a help question must be
    recorded as help, not bounced into a generic ack;
  * closing loop: a second short goodbye after the confirmation question is
    the confirmation itself — no infinite re-asking (the flag was never set);
  * agenda bounds: reaching the agenda-question helper with the agenda
    exhausted used to raise IndexError and drop the turn.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dialogue import Agent, reply_looks_broken  # noqa: E402


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


class FSMCloseAndRefusalTests(unittest.TestCase):
    """2026-08-29 P-CLOSE/P-ACK/P-ANCHOR (the live post-mortem call):

    * "давай, пока" must END the call (was left open by the old closing
      regex) and NOT demand a "хорошо или плохо" anchor afterwards;
    * "нет спасибо" is honoured (no follow-up push) and arms the fast close
      — a goodbye or silence after it ends the call without re-confirming;
    * a FIRST short goodbye in check_in still gets its single confirmation
      (mishear guard for «Да, всё хорошо» ↔ «До свидания»).
    """

    def setUp(self):
        self.agent = Agent(llm=None)
        self.agent.start_check_in()

    def test_davai_poka_ends_the_call(self):
        a = self.agent
        a.plan_reply("да, всё хорошо")          # close topic 0
        p = a.plan_reply("давай, пока")
        self.assertTrue(p.get("terminal"),
                        "«давай, пока» must finish the call")
        self.assertNotIn("хорошо или плохо", (p.get("fallback") or ""))
        self.assertEqual(a.mode, "closing")

    def test_net_spasibo_is_honoured_and_arms_fast_close(self):
        a = self.agent
        a.plan_reply("да, всё хорошо")
        # short polite decline of a follow-up offer
        p = a.plan_reply("нет спасибо")
        fb = (p.get("fallback") or "").lower()
        self.assertFalse(p.get("terminal"))
        # NOT the pushing "добавите что-нибудь для близких?" and no "да,
        # конечно" — a warm stop with no follow-up question mark.
        self.assertNotIn("добавите", fb)
        self.assertNotIn("да, конечно", fb)
        self.assertNotIn("?", fb)
        # silence right after the honoured decline -> end, no anchor
        p2 = a.plan_reply("", reason="low_conf")
        self.assertTrue(p2.get("terminal"),
                        "silence after refusal must end the call")

    def test_goodbye_after_refusal_closes_directly(self):
        a = self.agent
        a.plan_reply("да, всё хорошо")
        a.plan_reply("нет спасибо")            # honoured -> fast close armed
        p = a.plan_reply("пока")               # even bare «пока» now closes
        self.assertTrue(p.get("terminal"))
        self.assertEqual(a.mode, "closing")

    def test_first_short_goodbye_still_confirms_once(self):
        a = self.agent
        a.plan_reply("да, всё хорошо")
        p = a.plan_reply("до свидания")
        self.assertFalse(p.get("terminal"))
        self.assertIn("прощаетесь", (p.get("fallback") or ""))
        # the confirmation itself closes
        p2 = a.plan_reply("до свидания")
        self.assertTrue(p2.get("terminal"))

    def test_no_anchor_after_goodbye_silence(self):
        a = self.agent
        a.plan_reply("да, всё хорошо")
        p = a.plan_reply("до свидания")         # confirm-ask
        self.assertFalse(p.get("terminal"))
        p2 = a.plan_reply("", reason="low_conf")  # silence during confirm
        self.assertTrue(p2.get("terminal"))
        self.assertNotIn("хорошо или плохо", (p2.get("fallback") or ""))


class DialogueSafetyRecoveryTests(unittest.TestCase):
    """The dialogue FSM must recover together with the SafetyEngine.

    UNCERTAIN_RED is deliberately recoverable. Keeping the qualitative FSM
    state at SAFETY_ACTIVE after SafetyEngine returns OK suppresses the LLM
    for every later turn and makes the rest of the call scripted.
    """

    def setUp(self):
        self.agent = Agent(llm=None)
        self.agent.start_check_in()
        self.agent._last_confidence = 0.9

    def test_uncertain_red_positive_returns_to_checkin(self):
        a = self.agent
        a.plan_reply("плохо")
        a.plan_reply("не знаю")
        self.assertEqual(a.mode, "safety_confirm")

        plan = a.plan_reply("всё хорошо")

        self.assertEqual(a.mode, "check_in")
        self.assertEqual(a.status, "ok")
        self.assertFalse(plan.get("terminal"))

    def test_uncertain_symptom_stays_in_confirmation_not_active(self):
        a = self.agent
        a.plan_reply("плохо")

        plan = a.plan_reply("не знаю")

        self.assertEqual(a.mode, "safety_confirm")
        self.assertEqual(a.status, "attention")
        self.assertTrue(a._clearing)
        self.assertTrue(plan.get("fallback"))

    def test_danger_interrupts_side_question_immediately(self):
        a = self.agent
        a.plan_reply("А как у вас дела?")
        self.assertEqual(a._fsm.state, a._fsm.SIDE_QUESTION)

        plan = a.plan_reply("вызовите скорую")

        self.assertTrue(plan.get("terminal"))
        self.assertEqual(a._fsm.state, a._fsm.SIDE_QUESTION)
        self.assertEqual(a.status, "alert")
        self.assertTrue(a.done)
        self.assertEqual(a.safety.state, "CONFIRMED_RED")

    def test_question_mark_cannot_bypass_safety_classification(self):
        for text in (
                "У меня сильно болит грудь, что делать?",
                "Я упала, что теперь делать?",
                "Мне нужен врач, что делать?"):
            a = Agent(llm=None)
            a.start_check_in()
            a._last_confidence = 0.9

            plan = a.plan_reply(text)

            self.assertEqual(a._fsm.state, a._fsm.SAFETY_ACTIVE, text)
            self.assertEqual(a.status, "alert", text)
            self.assertTrue(plan.get("terminal"), text)
            self.assertTrue(plan.get("fallback"), text)


class DialoguePhaseExitTests(unittest.TestCase):
    def setUp(self):
        self.agent = Agent(llm=None)
        self.agent.start_check_in()
        self.agent._last_confidence = 0.9

    def test_positive_after_clarify_returns_to_checkin(self):
        a = self.agent
        a.plan_reply("")
        self.assertEqual(a.mode, "clarify")

        a.plan_reply("всё хорошо")

        self.assertEqual(a.mode, "check_in")

    def test_unrelated_wellness_answer_leaves_help_phase(self):
        a = self.agent
        a.plan_reply("мне нужна помощь")
        self.assertEqual(a._fsm.state, a._fsm.HELP)

        a.plan_reply("спала хорошо")

        self.assertEqual(a.mode, "check_in")
        self.assertNotEqual(a._fsm.state, a._fsm.HELP)


class PromiseGuardTests(unittest.TestCase):
    def test_first_person_action_promises_are_rejected(self):
        for text in (
                "Я позвоню вашей дочери.",
                "Сейчас вызову врача.",
                "Я отправлю сообщение родным.",
                "Я предупрежу близких.",
                "Я организую помощь."):
            self.assertTrue(reply_looks_broken(text), text)

    def test_record_only_language_is_allowed(self):
        self.assertFalse(reply_looks_broken(
            "Я всё записала, близкие это увидят."))

    def test_blocking_reply_falls_back_before_commit(self):
        class _PromiseLLM:
            def chat_stream(self, history):
                yield "Я позвоню вашей дочери."

        a = Agent(llm=_PromiseLLM())
        a.start_check_in()
        a._last_confidence = 0.9
        reply = a.reply("Сегодня всё хорошо")

        self.assertNotIn("позвоню", reply.lower())
        self.assertEqual(a._last_reply, reply)


if __name__ == "__main__":
    unittest.main(verbosity=2)