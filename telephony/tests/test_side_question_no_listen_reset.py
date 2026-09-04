"""Regression: side-question resume must not reset good_path to LISTEN."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation_system.agenda.topics import GOOD_PROBE_SUBTOPICS
from conversation_system.domain.fsm_types import CallPhase
from conversation_system.integration.facade import ConversationFacade


class SideQuestionNoListenResetTests(unittest.TestCase):
    def test_sleep_answer_after_side_question_no_mood_repeat(self):
        """mood → sleep slot → side Q → «спал хорошо» stays on sleep agenda."""
        facade = ConversationFacade()
        handle, _ = facade.begin_call(call_id="side-sleep-resume", greeting_played=True)

        p1 = facade.plan_turn(handle, transcript="хорошо", stt_confidence=0.9)
        facade.commit_turn(handle, p1, p1.spoken_reply)

        p2 = facade.plan_turn(
            handle, transcript="бодрое настроение", stt_confidence=0.9)
        facade.commit_turn(handle, p2, p2.spoken_reply)

        session = facade._get_session(handle)  # noqa: SLF001
        self.assertIn("настроение", session.agenda.covered_slots())
        sleep_idx_before = session.agenda.good_probe_index
        self.assertGreaterEqual(sleep_idx_before, 1)

        side = facade.plan_turn(
            handle, transcript="а кто вы такая?", stt_confidence=0.9)
        self.assertEqual(side.meta.get("goal_kind"), "answer_side")
        facade.commit_turn(
            handle,
            side,
            "Я Вера из Имвера, голосовой помощник заботы.",
        )

        session = facade._get_session(handle)  # noqa: SLF001
        self.assertEqual(session.fsm.phase, CallPhase.SIDE_ANSWER)
        saved_idx = session.agenda.interruption.return_slot_index
        self.assertGreaterEqual(saved_idx, 1)
        self.assertEqual(
            session.agenda.interruption.return_phase,
            CallPhase.GOOD_PATH.value,
        )

        resume = facade.plan_turn(
            handle, transcript="спал хорошо", stt_confidence=0.9)
        session = facade._get_session(handle)  # noqa: SLF001

        self.assertNotEqual(session.fsm.phase, CallPhase.LISTEN)
        self.assertEqual(session.fsm.phase, CallPhase.GOOD_PATH)
        self.assertNotEqual(session.agenda.good_probe_index, 0)
        self.assertIn("настроение", session.agenda.covered_slots())
        self.assertEqual(session.agenda.covered_slots().count("настроение"), 1)
        intent = resume.meta.get("intent") or ""
        self.assertIn("сон", intent.lower())
        self.assertIn("Never repeat: настроение", intent)

    def test_wellness_mood_sleep_plans_each_asked_once(self):
        """Full good path: each probe slot asked at most once (no repeats)."""
        facade = ConversationFacade()
        handle, _ = facade.begin_call(call_id="side-all-slots", greeting_played=True)
        answers = {
            "самочувствие": "хорошо",
            "настроение": "бодрое настроение",
            "сон": "спал нормально",
            "планы": "погуляю в парке",
        }
        asked_slots: list[str] = []
        p0 = facade.plan_turn(handle, transcript="хорошо", stt_confidence=0.9)
        facade.commit_turn(handle, p0, p0.spoken_reply)
        for slot in GOOD_PROBE_SUBTOPICS:
            if slot == "самочувствие":
                continue
            plan = facade.plan_turn(
                handle,
                transcript=answers.get(slot, "хорошо"),
                stt_confidence=0.9,
            )
            intent = plan.meta.get("intent") or ""
            if f"Required slot: {slot}" in intent or slot in intent.lower():
                asked_slots.append(slot)
            facade.commit_turn(handle, plan, plan.spoken_reply)
        session = facade._get_session(handle)  # noqa: SLF001
        covered = session.agenda.covered_slots()
        for slot in ("настроение", "сон", "планы"):
            self.assertLessEqual(covered.count(slot), 1)
        self.assertNotEqual(session.fsm.phase, CallPhase.LISTEN)


if __name__ == "__main__":
    unittest.main(verbosity=2)
