"""Phase 4 observer — spoken-state sync, corrections, lifecycle, repair/ack."""
from __future__ import annotations

import os
import sys
import unittest
from typing import Iterator, List
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation_system.domain.pending_question import PendingQuestionType
from conversation_system.domain.understanding import SpeechAct
from conversation_system.integration.facade import ConversationFacade
from conversation_system.observer import Observer
from conversation_system.turn._classifiers import is_ack, is_repair
from conversation_system.turn._cleaners import clean_transcript
from conversation_system.turn.analyzer import (
    TurnAnalyzer,
    extract_correction_focus,
)


class _SideAnswerLlm:
    """LLM that speaks different text than pool fallback."""

    def chat_stream(self, _messages, **_kwargs) -> Iterator[str]:
        yield (
            "Я звоню, чтобы узнать как вы себя чувствуете — "
            "это сервис Имвера для близких. Как вы сегодня?"
        )


class SpokenStateSyncTests(unittest.TestCase):
    def test_commit_uses_actual_spoken_not_pool_fallback(self):
        facade = ConversationFacade()
        handle, _ = facade.begin_call(call_id="p4-spoken", greeting_played=True)
        plan = facade.plan_turn(
            handle, transcript="зачем вы звоните?", stt_confidence=0.9)
        pool_fallback = plan.spoken_reply
        actual = (
            "Я звоню, чтобы узнать как вы себя чувствуете — "
            "это сервис Имвера. Как вы сегодня?"
        )
        self.assertNotEqual(actual, pool_fallback)
        facade.commit_turn(handle, plan, actual)
        session = facade._get_session(handle)  # noqa: SLF001
        self.assertEqual(session.memory.last_reply, actual)
        self.assertEqual(session.memory.last_question, actual)
        if session.memory.pending_question is not None:
            self.assertEqual(
                session.memory.pending_question.prompt,
                actual,
            )


class CorrectionExtractionTests(unittest.TestCase):
    def test_extract_correction_focus_supersedes_head_for_back(self):
        old, new = extract_correction_focus(
            "нет, не голова, я ошиблась — спина болит")
        self.assertEqual(old, "голова")
        self.assertEqual(new, "спина")

    def test_analyzer_sets_spina_on_correction_path(self):
        analyzer = TurnAnalyzer()
        u = analyzer.analyze(
            "нет, не голова, я ошиблась — спина болит",
            confidence=0.9,
        )
        self.assertEqual(u.symptom_focus, "спина")

    def test_observer_updates_active_symptom_on_correction(self):
        facade = ConversationFacade()
        handle, _ = facade.begin_call(call_id="p4-corr", greeting_played=True)
        facade.plan_turn(handle, transcript="голова болит", stt_confidence=0.9)
        plan = facade.plan_turn(
            handle,
            transcript="нет, не голова, я ошиблась — спина болит",
            stt_confidence=0.9,
        )
        session = facade._get_session(handle)  # noqa: SLF001
        self.assertEqual(session.memory.active_symptom, "спина")
        facade.commit_turn(handle, plan, plan.spoken_reply)


class QuestionLifecycleTests(unittest.TestCase):
    def test_side_question_cleared_after_answer(self):
        facade = ConversationFacade()
        handle, _ = facade.begin_call(call_id="p4-q-life", greeting_played=True)
        q_plan = facade.plan_turn(
            handle, transcript="зачем вы звоните?", stt_confidence=0.9)
        facade.commit_turn(
            handle,
            q_plan,
            "Я звоню, чтобы узнать как вы — это Имвера, запись для близких.",
        )
        session = facade._get_session(handle)  # noqa: SLF001
        self.assertEqual(session.memory.unanswered_user_questions, [])
        next_plan = facade.plan_turn(
            handle, transcript="спал хорошо", stt_confidence=0.9)
        directive = session.memory.next_directive or ""
        self.assertNotIn("зачем вы звоните", directive.lower())
        self.assertNotIn("зачем звон", directive.lower())
        self.assertTrue(next_plan.spoken_reply)


class RepairAckSpeechActTests(unittest.TestCase):
    def test_repair_patterns_not_classified_as_question(self):
        cases = (
            "что вы спросили?",
            "я не понял вопрос",
            "я не поняла вопрос",
            "что за вопрос",
            "можно ещё раз вопрос",
            "повторите вопрос",
        )
        analyzer = TurnAnalyzer()
        for text in cases:
            with self.subTest(text=text):
                self.assertTrue(is_repair(text))
                u = analyzer.analyze(text, confidence=0.9)
                self.assertEqual(u.speech_act, SpeechAct.REPAIR)

    def test_ack_not_junk_empty(self):
        for text in ("понятно", "ясно", "ладно"):
            with self.subTest(text=text):
                self.assertTrue(is_ack(text))
                cleaned = clean_transcript(text)
                self.assertEqual(cleaned, text)
                u = TurnAnalyzer().analyze(text, confidence=0.9)
                self.assertEqual(u.speech_act, SpeechAct.ACK)
        u_good = TurnAnalyzer().analyze("хорошо", confidence=0.9)
        self.assertEqual(u_good.speech_act, SpeechAct.ACK)

    def test_repair_repeats_last_question_in_script(self):
        facade = ConversationFacade()
        handle, _ = facade.begin_call(call_id="p4-repair", greeting_played=True)
        first = facade.plan_turn(
            handle, transcript="нормально", stt_confidence=0.9)
        question = "Как настроение сегодня?"
        facade.commit_turn(handle, first, question)
        repair_plan = facade.plan_turn(
            handle, transcript="что вы спросили?", stt_confidence=0.9)
        self.assertIn("?", repair_plan.spoken_reply)
        session = facade._get_session(handle)  # noqa: SLF001
        self.assertEqual(repair_plan.spoken_reply, session.memory.last_question)


class LlmConversationTurnTests(unittest.TestCase):
    def test_good_path_plan_allows_llm(self):
        saved = os.environ.get("MOSS_DIALOGUE_LLM_CHECKIN")
        os.environ["MOSS_DIALOGUE_LLM_CHECKIN"] = "1"
        try:
            facade = ConversationFacade()
            handle, _ = facade.begin_call(call_id="p4-llm", greeting_played=True)
            plan = facade.plan_turn(
                handle, transcript="хорошо, спасибо", stt_confidence=0.9)
            self.assertTrue(plan.meta.get("allow_llm"))
            self.assertFalse(
                plan.meta.get("allow_llm") is False and plan.stream is False)
        finally:
            if saved is None:
                os.environ.pop("MOSS_DIALOGUE_LLM_CHECKIN", None)
            else:
                os.environ["MOSS_DIALOGUE_LLM_CHECKIN"] = saved

    def test_mirror_llm_stream_used_when_wired(self):
        from core.call_mirror import CallMirror
        from core.conversation_v2_bridge import begin_v2_call, plan_turn_for_call
        from core.state import CallContext

        ctx = CallContext(call_id="mirror-llm", agent=CallMirror(llm=_SideAnswerLlm()))
        begin_v2_call(ctx, caller_id="", mode="check_in")
        ctx.agent.llm = _SideAnswerLlm()
        legacy, spoke = plan_turn_for_call(
            ctx,
            ctx.agent,
            transcript="зачем вы звоните?",
            stt_confidence=0.9,
        )
        self.assertTrue(spoke)
        self.assertTrue(legacy.get("allow_llm"))
        chunks = list(ctx.agent.reply_stream(legacy))
        self.assertTrue(chunks)
        self.assertIn("Имвера", "".join(chunks))


class ObserverBlockingTests(unittest.TestCase):
    def test_llm_enricher_skipped_by_default(self):
        mem = __import__(
            "conversation_system.memory.state",
            fromlist=["ConversationMemory"],
        ).ConversationMemory(call_id="blk")
        obs = Observer(llm=object())
        u = TurnAnalyzer().analyze("голова болит", confidence=0.9)
        with mock.patch(
            "conversation_system.observer.llm_enricher.observer_llm_blocking_enabled",
            return_value=False,
        ):
            with mock.patch.object(
                obs._llm_enricher, "enrich", return_value=None) as enrich:
                patch = obs.observe_turn(mem, u)
                enrich.assert_not_called()
        self.assertFalse(patch.llm_enriched)


if __name__ == "__main__":
    unittest.main()
