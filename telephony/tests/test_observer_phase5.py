"""Phase 5 P0 — stream truncation, goal arbitration, side-question resume."""
from __future__ import annotations

import os
import sys
import unittest
from typing import Iterator, List
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation_system.domain.fsm_types import CallPhase
from conversation_system.domain.understanding import ResponseGoalKind, SpeechAct
from conversation_system.integration.facade import ConversationFacade
from conversation_system.reply.llm_context import compose_turn_directive
from conversation_system.turn.analyzer import TurnAnalyzer
from core.events import reply_segments


class _MultiSentenceLlm:
    def reply_stream(self, _plan):
        yield (
            "Рада это слышать, спасибо что поделились. "
            "Как настроение сегодня?"
        )


class ReplySegmentsStreamTests(unittest.TestCase):
    def test_multi_sentence_stream_yields_all_segments(self):
        agent = mock.Mock()
        agent.reply_stream = lambda _plan: iter([
            "Рада это слышать, спасибо. ",
            "Как спали ночью?",
        ])
        plan = {"text": "хорошо", "allow_llm": True}
        segments = list(reply_segments(agent, plan, max_segments=3))
        joined = " ".join(segments)
        self.assertIn("спали", joined.lower())
        self.assertIn("?", joined)
        self.assertGreaterEqual(len(segments), 1)

    def test_early_comma_does_not_truncate_tail(self):
        """Early-first-sound comma cut must not stop reading the LLM stream."""
        chunks = [
            "Понимаю, ",
            "это важно для вас, ",
            "и мне приятно слушать. ",
            "Как настроение сегодня?",
        ]

        class _Agent:
            def reply_stream(self, _plan):
                for c in chunks:
                    yield c

        segs = list(reply_segments(_Agent(), {"allow_llm": True}, max_segments=4))
        combined = " ".join(segs)
        self.assertIn("важно", combined.lower())
        self.assertIn("настроение", combined.lower())
        self.assertGreaterEqual(len(segs), 2)


class GoalArbitrationTests(unittest.TestCase):
    def test_good_path_completes_to_record_notify_not_ask_topic(self):
        facade = ConversationFacade()
        handle, _ = facade.begin_call(call_id="p5-wrap", greeting_played=True)
        session = facade._get_session(handle)  # noqa: SLF001
        p0 = facade.plan_turn(handle, transcript="хорошо", stt_confidence=0.9)
        facade.commit_turn(handle, p0, p0.spoken_reply)
        for answer in ("бодрое настроение", "спал спокойно"):
            plan = facade.plan_turn(
                handle, transcript=answer, stt_confidence=0.9)
            facade.commit_turn(handle, plan, plan.spoken_reply)
        wrap_plan = facade.plan_turn(
            handle, transcript="погуляю в парке", stt_confidence=0.9)
        facade.commit_turn(handle, wrap_plan, wrap_plan.spoken_reply)
        session = facade._get_session(handle)  # noqa: SLF001
        self.assertIn(
            session.fsm.phase,
            (CallPhase.RECORD_NOTIFY, CallPhase.CLOSING),
        )
        self.assertEqual(wrap_plan.meta.get("goal_kind"), "wrap_up")
        self.assertFalse(wrap_plan.meta.get("allow_llm"))


class SideQuestionResumeTests(unittest.TestCase):
    def test_side_question_resumes_sleep_not_mood_repeat(self):
        facade = ConversationFacade()
        handle, _ = facade.begin_call(call_id="p5-side", greeting_played=True)
        p1 = facade.plan_turn(handle, transcript="хорошо", stt_confidence=0.9)
        facade.commit_turn(handle, p1, p1.spoken_reply)
        p2 = facade.plan_turn(
            handle, transcript="бодрое настроение", stt_confidence=0.9)
        facade.commit_turn(handle, p2, p2.spoken_reply)
        session = facade._get_session(handle)  # noqa: SLF001
        self.assertIn("настроение", session.agenda.covered_slots())
        side = facade.plan_turn(
            handle,
            transcript="а кто вы такая?",
            stt_confidence=0.9,
        )
        self.assertEqual(side.meta.get("goal_kind"), "answer_side")
        facade.commit_turn(
            handle,
            side,
            "Я Вера из Имвера, голосовой помощник заботы.",
        )
        resume = facade.plan_turn(
            handle, transcript="понятно", stt_confidence=0.9)
        session = facade._get_session(handle)  # noqa: SLF001
        self.assertEqual(session.fsm.phase, CallPhase.GOOD_PATH)
        intent = resume.meta.get("intent") or ""
        self.assertIn("сон", intent.lower())
        self.assertIn("Never repeat: настроение", intent)
        self.assertEqual(session.agenda.covered_slots().count("настроение"), 1)

    def test_full_good_path_slot_counts(self):
        facade = ConversationFacade()
        handle, _ = facade.begin_call(call_id="p5-slots", greeting_played=True)
        steps = [
            ("хорошо", None),
            ("бодрое", "настроение"),
            ("кто вы?", "side"),
            ("ясно", None),
            ("спал хорошо", "сон"),
            ("погуляю", "планы"),
        ]
        for text, _ in steps:
            plan = facade.plan_turn(handle, transcript=text, stt_confidence=0.9)
            spoken = plan.spoken_reply
            if text == "кто вы?":
                spoken = "Я Вера из Имвера."
            facade.commit_turn(handle, plan, spoken)
        session = facade._get_session(handle)  # noqa: SLF001
        covered = session.agenda.covered_slots()
        self.assertEqual(covered.count("настроение"), 1)
        self.assertEqual(covered.count("сон"), 1)
        self.assertEqual(covered.count("планы"), 1)


class RepairLifecycleTests(unittest.TestCase):
    def test_repair_not_tracked_as_user_question(self):
        facade = ConversationFacade()
        handle, _ = facade.begin_call(call_id="p5-repair", greeting_played=True)
        first = facade.plan_turn(handle, transcript="нормально", stt_confidence=0.9)
        facade.commit_turn(handle, first, "Как настроение?")
        repair = facade.plan_turn(
            handle, transcript="что вы спросили?", stt_confidence=0.9)
        session = facade._get_session(handle)  # noqa: SLF001
        self.assertEqual(repair.meta.get("goal_kind"), "repair")
        self.assertEqual(session.memory.unanswered_user_questions, [])


class CorrectionDirectiveTests(unittest.TestCase):
    def test_correction_directive_uses_spina_not_golova(self):
        facade = ConversationFacade()
        handle, _ = facade.begin_call(call_id="p5-corr-dir", greeting_played=True)
        facade.plan_turn(handle, transcript="голова болит", stt_confidence=0.9)
        plan = facade.plan_turn(
            handle,
            transcript="нет, не голова, я ошиблась — спина болит",
            stt_confidence=0.9,
        )
        session = facade._get_session(handle)  # noqa: SLF001
        intent = plan.meta.get("intent") or ""
        self.assertIn("спина", intent.lower())
        self.assertEqual(session.memory.active_symptom, "спина")


class IntentMergeTests(unittest.TestCase):
    def test_compose_turn_directive_merges_all_parts(self):
        text = compose_turn_directive(
            observer_handling="Ответь на вопрос абонента.",
            goal_must_do="Спроси ТОЛЬКО о сне.",
            current_slot="сон",
            covered_slots=("настроение",),
            forbidden_slots=("настроение",),
        )
        self.assertIn("User handling:", text)
        self.assertIn("Required action:", text)
        self.assertIn("Required slot: сон", text)
        self.assertIn("Covered: настроение", text)
        self.assertIn("Never repeat: настроение", text)


class PoolPromiseTests(unittest.TestCase):
    def test_no_fake_delivery_confirmations_in_pools(self):
        from conversation_system.reply.pools import all_unique_spoken_lines

        forbidden = (
            "уже передали", "уже видят", "оповестила", "близкие оповещены",
            "передала близким", "оповестила их",
        )
        for line in all_unique_spoken_lines():
            low = line.lower()
            for phrase in forbidden:
                self.assertNotIn(
                    phrase, low,
                    msg=f"fake delivery in pool: {line!r}",
                )


class SemanticCloseTests(unittest.TestCase):
    def test_arbitrary_two_words_do_not_close_probe(self):
        from conversation_system.agenda.manager import AgendaManager
        from conversation_system.turn.analyzer import TurnAnalyzer

        agenda = AgendaManager.from_canonical()
        agenda.on_good_path = True
        agenda.good_probe_index = 0
        agenda._seek_topic("проба хорошо")  # noqa: SLF001
        u = TurnAnalyzer().analyze("да хорошо", confidence=0.9)
        self.assertFalse(agenda.semantic_close(u))


if __name__ == "__main__":
    unittest.main()
