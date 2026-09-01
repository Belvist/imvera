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
        a = Agent(llm=None)
        # Qwen3-ASR now honest: None confidence = unknown (U9). Existing
        # dialogue tests pre-date Qwen3 and expect high confidence.
        # Keep high unless test explicitly sets low.
        orig = a.plan_reply
        def wrapped(text, reason=None):
            if a._last_confidence is None:
                a._last_confidence = 0.9
            return orig(text, reason=reason)
        a.plan_reply = wrapped
        a._last_confidence = 0.9
        return a

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
        # NEW CONTRACT (prompt-cache): the system prompt is CONSTANT
        # (no per-turn objective — that invalidated the llama.cpp KV
        # cache every turn, +1-2 s). The context rides on the CURRENT
        # user message as labeled lines — SKILL.state, not a raw
        # conversation dump.
        sys_msgs = [m for m in hist if m["role"] == "system"]
        self.assertEqual(len(sys_msgs), 1)
        self.assertNotIn("Цель текущего ответа", sys_msgs[0]["content"])
        user_msgs = [m for m in hist if m["role"] == "user"]
        self.assertTrue(any("текущая тема" in m["content"]
                            or "уже обсуждено" in m["content"]
                            or "последний вопрос" in m["content"]
                            for m in user_msgs),
                        "SKILL.state context must ride on the current user turn")
        # the context lines are labeled blocks, not the message body start
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

    # ---- D2: LLM-driven _a_ok (phase 2) ----

    def test_llm_driven_ok_variety(self):
        """Same confirmation → LLM-formulated replies, not identical canned."""
        _n = [0]
        _variants = [
            "Ох, как приятно! А как сон пошёл?",
            "Рада это слышать! А давайте поговорим о сне?",
            "Замечательно! А как прошла ночь?",
            "Отлично! И что насчёт сна — всё ли хорошо?",
            "Приятно! Перейдём к вопросу о сне?",
        ]

        class _MockLLM:
            def chat_stream(self, history):
                _n[0] += 1
                yield _variants[(_n[0] - 1) % len(_variants)]

            def chat(self, history):
                return _variants[(_n[0] - 1) % len(_variants)]

        a = Agent(llm=_MockLLM())
        a.start_check_in()
        a._last_confidence = 0.9
        replies = []
        for _ in range(5):
            plan = a.plan_reply("всё хорошо")
            streamed = list(a.reply_stream(plan))
            reply = "".join(streamed) if streamed else plan.get("fallback", "")
            a.commit_reply(reply)
            replies.append(reply)
        # All replies should be different (LLM-driven variety)
        self.assertEqual(len(set(replies)), len(replies),
                         "LLM should produce varied answers for same input")
        # None should be a canned fallback
        for r in replies:
            self.assertNotIn("нужна ли помощь", r.lower())

    def test_llm_remembers_topic(self):
        """LLM reply includes the current topic context."""
        class _MockLLM:
            def chat_stream(self, history):
                # Last user msg should contain the topic context
                last_user = ""
                for m in reversed(history):
                    if m["role"] == "user":
                        last_user = m["content"]
                        break
                # The context note should mention the topic
                yield "Хорошо! Про сон — а как вы спите?"

            def chat(self, history):
                return "Хорошо! Про сон — а как вы спите?"

        a = Agent(llm=_MockLLM())
        a.start_check_in()
        a._last_confidence = 0.9
        # Advance to topic "сон"
        plan = a.plan_reply("всё хорошо")
        a.reply_stream(plan)
        a.commit_reply(plan.get("fallback", ""))
        plan2 = a.plan_reply("всё хорошо")
        history = a._build_history()
        topic_in_context = any("сон" in (m.get("content") or "")
                               for m in history)
        self.assertTrue(topic_in_context,
                        "topic should appear in LLM context")

    def test_null_llm_fallback(self):
        """When LLM is None, reply_stream yields meaningful fallback, not empty."""
        a = Agent(llm=None)
        a.start_check_in()
        a._last_confidence = 0.9
        plan = a.plan_reply("всё хорошо")
        replies = list(a.reply_stream(plan))
        self.assertTrue(replies, "reply_stream should yield something")
        combined = "".join(replies)
        self.assertTrue(len(combined) > 0, "fallback reply should not be empty")
        self.assertNotIn("нужна ли помощь", combined.lower())

    # ---- Phase 3.2: variety tests ----

    def test_variety_no_repeat(self):
        """20 confirmation turns → low repeat rate (pool rotation)."""
        a = self._agent()
        questions = []
        for _ in range(20):
            plan = a.plan_reply("всё хорошо")
            fb = plan.get("fallback") or ""
            questions.append(fb)
        repeats = len(questions) - len(set(questions))
        self.assertLessEqual(repeats, 3,
                             f"too many repeats: {repeats}/20")

    def test_variety_within_call(self):
        """10 turns in one call → questions stay fresh."""
        a = Agent(llm=None)
        a.start_check_in()
        a._last_confidence = 0.9
        questions = []
        for _ in range(10):
            plan = a.plan_reply("всё хорошо")
            fb = plan.get("fallback") or ""
            questions.append(fb)
        repeats = len(questions) - len(set(questions))
        self.assertLessEqual(repeats, 2,
                             f"too many repeats in one call: {repeats}/10")


if __name__ == "__main__":
    unittest.main(verbosity=2)