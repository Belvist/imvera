"""Dialogue mode machine: the conversation is NOT a questionnaire anymore.

The Agent is mode-driven (companion by default) and four regressions are
fixed:
  A. the current user turn is not duplicated in the LLM history;
  B. the reply objective is part of the SYSTEM context, never a user msg;
  C. no forced question after every reply;
  D. no auto-finish after N answers — only an explicit goodbye or a
     confirmed danger ends the conversation.
"""

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from core.dialogue import Agent, MVERA_GREETING  # noqa: E402


class ModeMachineTests(unittest.TestCase):
    def _agent(self):
        return Agent(llm=None)

    def test_default_mode_is_companion(self):
        a = self._agent()
        self.assertEqual(a.mode, "companion")
        self.assertEqual(a.step, 0)

    # ---- A: no duplicate user turn ----
    def test_user_turn_not_duplicated_in_history(self):
        a = self._agent()
        a.plan_reply("внучка сегодня приезжала")
        user_msgs = [m["content"] for m in a._build_history()
                     if m["role"] == "user"]
        self.assertEqual(user_msgs.count("внучка сегодня приезжала"), 1)
        self.assertEqual(len(a.llm_history), 1)

    # ---- B: objective is system context, never a user message ----
    def test_intent_is_system_context(self):
        a = self._agent()
        a.plan_reply("всё хорошо")
        a.last_intent = "естественно порадоваться и продолжить беседу"
        hist = a._build_history()
        # NEW CONTRACT (prompt-cache): the system prompt is CONSTANT (no
        # per-turn objective — that invalidated the llama.cpp KV cache every
        # turn, +1-2 s). The objective rides on the CURRENT user message as
        # a bracketed note.
        sys_msgs = [m for m in hist if m["role"] == "system"]
        self.assertEqual(len(sys_msgs), 1)
        self.assertNotIn("Цель текущего ответа", sys_msgs[0]["content"])
        user_msgs = [m for m in hist if m["role"] == "user"]
        self.assertTrue(any("(Цель ответа:" in m["content"]
                            for m in user_msgs),
                        "objective must ride on the current user turn")
        # the objective is a bracketed note, not the message body start
        for m in user_msgs:
            self.assertFalse(m["content"].startswith("("))

    # ---- C: no forced question after every reply ----
    def test_ok_reply_is_not_a_question(self):
        a = self._agent()
        plan = a.plan_reply("всё хорошо")
        # SPEED FAST PATH: short confirmations are scripted (intent=None),
        # the fallback must still never push the help question.
        intent = plan.get("intent") or ""
        fb = plan.get("fallback") or ""
        self.assertNotIn("нужна ли помощь", (intent + " " + fb).lower())
        self.assertNotIn("спросить", (intent + " " + fb).lower())

    # ---- D: no auto-finish after N answers ----
    def test_no_auto_finish_after_two_answers(self):
        a = self._agent()
        for t in ("всё хорошо", "нет", "да"):
            a.plan_reply(t)
        self.assertFalse(a.done)
        self.assertEqual(a.status, "ok")

    def test_long_chat_stays_open_until_goodbye(self):
        a = self._agent()
        for t in ("внучка сегодня приезжала", "да, давно не виделись",
                  "чай попили", "она надолго заходила?", "да, до вечера",
                  "ну всё, пока-пока"):
            a.plan_reply(t)
        self.assertTrue(a.done)
        self.assertEqual(a.mode, "closing")
        self.assertEqual(a.status, "ok")

    def test_goodbye_ends_the_call(self):
        a = self._agent()
        a.plan_reply("внучка приезжала")
        plan = a.plan_reply("до свидания")
        self.assertTrue(plan.get("terminal"))
        self.assertTrue(a.done)
        self.assertEqual(a.mode, "closing")

    def test_bare_poka_does_not_close(self):
        a = self._agent()
        plan = a.plan_reply("пока нет")
        self.assertFalse(plan.get("terminal"))
        self.assertFalse(a.done)

    # ---- safety stays intact ----
    def test_confirmed_red_still_terminal(self):
        a = self._agent()
        plan = a.plan_reply("вызовите скорую")
        self.assertTrue(plan.get("terminal"))
        self.assertTrue(a.done)
        self.assertEqual(a.status, "alert")
        self.assertEqual(a.mode, "safety_active")

    def test_no_speech_is_clarify(self):
        a = self._agent()
        plan = a.plan_reply("")
        self.assertEqual(a.mode, "clarify")
        self.assertIsNone(plan.get("intent"))
        # 1st empty turn (2026-08-25): a yes/no WELLNESS ANCHOR instead of a
        # blind «Повторите» — whisper-tiny recognises «хорошо/плохо» nearly
        # perfectly, so the call moves forward on silence; 2nd: fixed calm
        # tapered-ladder line (drama dropped).
        self.assertIn(plan["fallback"], Agent.ANCHORS)
        plan2 = a.plan_reply("")
        self.assertEqual(plan2["fallback"], "Алло, вы меня слышите?")

    def test_possible_red_asks_control_question(self):
        a = self._agent()
        plan = a.plan_reply("плохо")
        self.assertEqual(a.mode, "safety_confirm")
        self.assertEqual(a.status, "attention")
        self.assertIn("уточнить", plan["intent"])

    def test_help_request_asks_what_needed(self):
        a = self._agent()
        plan = a.plan_reply("мне нужна помощь")
        self.assertEqual(a.mode, "check_in")
        self.assertEqual(a.status, "attention")
        self.assertIn("помощ", plan["intent"].lower())

    def test_ok_clears_after_control_question(self):
        a = self._agent()
        a.plan_reply("плохо")           # possible_red -> control question
        a.plan_reply("всё хорошо")      # clears
        self.assertEqual(a.status, "ok")
        self.assertFalse(a.done)

    def test_ok_does_not_clear_third_person_concern(self):
        a = self._agent()
        a.plan_reply("бабушка упала")
        a.plan_reply("нет")
        self.assertEqual(a.status, "attention")
        self.assertFalse(a.done)

    def test_unknown_keeps_status_and_continues(self):
        a = self._agent()
        plan = a.plan_reply("ну, как-то так")
        self.assertEqual(a.status, "unknown")
        self.assertFalse(a.done)
        self.assertIn("откликнуться", plan["intent"])

    # ---- check-in (service-initiated) ----
    def test_start_check_in_greets(self):
        a = self._agent()
        greeting = a.start_check_in()
        self.assertEqual(greeting, MVERA_GREETING)
        self.assertEqual(a.mode, "check_in")
        plan = a.plan_reply("всё хорошо")
        self.assertFalse(a.done)
        self.assertEqual(a.status, "ok")
        combined = ((plan.get("intent") or "") + " " +
                    (plan.get("fallback") or "")).lower()
        self.assertNotIn("нужна ли помощь", combined)

    def test_conversation_keeps_going_after_ok(self):
        a = self._agent()
        a.plan_reply("всё хорошо")
        a.plan_reply("внучка приезжала")
        self.assertFalse(a.done)
        self.assertEqual(a.status, "ok")


if __name__ == "__main__":
    unittest.main(verbosity=2)