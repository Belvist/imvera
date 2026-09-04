"""Regression tests for live calls 09a1b47cf731 and 793b79886881."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation_system.agenda.manager import AgendaManager
from conversation_system.agenda.topics import TOPIC_GOOD_PROBE, TOPIC_RECORD_NOTIFY
from conversation_system.domain.fsm_types import CallPhase, CallPhaseContext, FsmEvent
from conversation_system.domain.understanding import ResponseGoalKind
from conversation_system.domain.wellness import WellnessBand
from conversation_system.integration.facade import ConversationFacade
from conversation_system.memory.state import ConversationMemory
from conversation_system.policy.fsm import CallPhaseMachine
from conversation_system.reply.composer import ReplyComposer
from conversation_system.turn._classifiers import is_closing
from conversation_system.turn.analyzer import TurnAnalyzer
from core.call_mirror import CallMirror
from core.call_status import CallStatus, family_fields_for_finalize, resolve_family_status
from core.conversation_v2_bridge import begin_v2_call, plan_turn_for_call
from core.state import CallContext


class LiveCallClosingClassifierTests(unittest.TestCase):
    def test_vera_poka(self):
        self.assertTrue(is_closing("Вера пока"))

    def test_davay_pokover_typo(self):
        self.assertTrue(is_closing("Всё хорошо, всё давай поковер"))

    def test_bare_poka_at_end(self):
        self.assertTrue(is_closing("ну ладно, пока"))


class LiveCallMoodSlotAdvanceTests(unittest.TestCase):
    def setUp(self):
        self.agenda = AgendaManager.from_canonical()
        self.analyzer = TurnAnalyzer()

    def _enter_good_path(self):
        self.agenda.mark_question_asked()
        u = self.analyzer.analyze("всё отлично", confidence=0.9)
        self.agenda.mark_discussed(u)

    def test_mood_keyword_advances_slot(self):
        self._enter_good_path()
        self.assertEqual(self.agenda.current_good_slot(), "настроение")
        self.agenda.mark_question_asked()
        u = self.analyzer.analyze("настроение хорошее", confidence=0.9)
        self.agenda.mark_discussed(u)
        self.assertIn("настроение", self.agenda.covered_slots())
        self.assertEqual(self.agenda.current_good_slot(), "сон")

    def test_positive_feeling_on_mood_turn_advances(self):
        self._enter_good_path()
        self.agenda.mark_question_asked()
        u = self.analyzer.analyze("чувствую себя хорошо", confidence=0.9)
        self.assertTrue(self.agenda._good_probe_answered(u))
        self.agenda.mark_discussed(u)
        self.assertIn("настроение", self.agenda.covered_slots())
        self.assertEqual(self.agenda.current_good_slot(), "сон")


class LiveCallBadPathUnhandledTests(unittest.TestCase):
    def setUp(self):
        self.fsm = CallPhaseMachine()
        self.mem = ConversationMemory(call_id="bad-unhandled")
        self.agenda = AgendaManager.from_canonical()
        self.agenda.on_bad_path = True
        self.agenda.wellness_band = WellnessBand.BAD
        self.composer = ReplyComposer()

    def test_unhandled_bad_path_symptom_not_mood(self):
        ctx = CallPhaseContext(memory=self.mem, agenda=self.agenda)
        self.fsm.phase = CallPhase.BAD_PATH
        result = self.fsm.dispatch(ctx, FsmEvent.E_UNHANDLED)
        self.assertEqual(result.goal.kind, ResponseGoalKind.SYMPTOM_FOLLOWUP)
        reply = self.composer.compose(result.goal, self.mem, self.agenda)
        low = reply.text.lower()
        self.assertNotIn("настроение", low)
        self.assertTrue(
            "беспокоит" in low or "симптом" in low or "болит" in low,
            msg=reply.text,
        )


class CheckinLlmGateTests(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("MOSS_DIALOGUE_LLM_CHECKIN")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("MOSS_DIALOGUE_LLM_CHECKIN", None)
        else:
            os.environ["MOSS_DIALOGUE_LLM_CHECKIN"] = self._saved

    def _with_checkin_env(self, value: str) -> None:
        os.environ["MOSS_DIALOGUE_LLM_CHECKIN"] = value

    def test_symptom_turn_uses_pool_not_llm_when_checkin_off(self):
        self._with_checkin_env("0")
        facade = ConversationFacade()
        handle, _ = facade.begin_call(
            call_id="e26d5338aed8-regression",
            greeting_played=True,
        )
        plan = facade.plan_turn(
            handle,
            transcript="голова болит",
            stt_confidence=0.9,
        )
        self.assertFalse(plan.meta.get("allow_llm"))
        low = plan.spoken_reply.lower()
        self.assertTrue(
            "терпим" in low or "сильн" in low or "беспокоит" in low,
            msg=plan.spoken_reply,
        )
        self.assertNotIn("здравствуйте", low)

    def test_orchestrator_ignores_garbage_llm_on_symptom_checkin(self):
        self._with_checkin_env("0")

        class _GarbageLlm:
            def chat_stream(self, *_args, **_kwargs):
                yield "Здравствуйте! Как вы себе помочь?"

        ctx = CallContext(
            call_id="e26d5338aed8-orch",
            agent=CallMirror(llm=_GarbageLlm()),
        )
        begin_v2_call(ctx, mode="check_in")
        legacy, spoke = plan_turn_for_call(
            ctx,
            ctx.agent,
            transcript="голова болит",
            stt_confidence=0.9,
        )
        self.assertTrue(spoke)
        self.assertFalse(legacy.get("allow_llm"))
        reply = "".join(ctx.agent.reply_stream(legacy))
        low = reply.lower()
        self.assertTrue(
            "терпим" in low or "сильн" in low or "беспокоит" in low,
            msg=reply,
        )
        self.assertNotIn("здравствуйте", low)

    def test_good_path_allows_llm_when_checkin_on(self):
        self._with_checkin_env("1")
        facade = ConversationFacade()
        handle, _ = facade.begin_call(
            call_id="checkin-llm-on",
            greeting_played=True,
        )
        plan = facade.plan_turn(
            handle,
            transcript="хорошо",
            stt_confidence=0.9,
        )
        self.assertTrue(plan.meta.get("allow_llm"))


class LiveCallEndCallVerdictTests(unittest.TestCase):
    def test_bad_wellness_yellow_on_short_call(self):
        facade = ConversationFacade()
        handle, _ = facade.begin_call(
            call_id="793b79886881-regression",
            greeting_played=True,
        )
        plan = facade.plan_turn(
            handle,
            transcript="плохо, голова болит",
            stt_confidence=0.9,
        )
        facade.commit_turn(handle, plan, plan.spoken_reply)
        summary = facade.end_call(handle)
        self.assertIn(summary.verdict, ("attention", "alert"))
        fields = family_fields_for_finalize(
            "ok",
            notes=list(summary.notes),
            wellness_band="bad",
        )
        self.assertEqual(fields["family_status"], "yellow")

    def test_resolve_family_status_bad_wellness_floor(self):
        self.assertEqual(
            resolve_family_status("ok", wellness_band="bad"),
            CallStatus.YELLOW,
        )


class Call7836b400BadPathRegressionTests(unittest.TestCase):
    """Regression for live call 7836b400662d — bad-path probe pacing."""

    def setUp(self):
        os.environ["MOSS_DIALOGUE_LLM_CHECKIN"] = "0"
        self.facade = ConversationFacade()
        self.handle, _ = self.facade.begin_call(
            call_id="7836b400662d-regression",
            greeting_played=True,
        )

    def tearDown(self):
        os.environ.pop("MOSS_DIALOGUE_LLM_CHECKIN", None)

    def test_symptoms_in_first_turn_skip_generic_probe(self):
        plan = self.facade.plan_turn(
            self.handle,
            transcript="плохо голова болит тошнота",
            stt_confidence=0.9,
        )
        self.facade.commit_turn(self.handle, plan, plan.spoken_reply)
        low = plan.spoken_reply.lower()
        self.assertNotIn("что именно беспокоит", low)
        self.assertTrue(
            "терпим" in low or "сильн" in low or "боль" in low,
            msg=plan.spoken_reply,
        )

    def test_mild_severity_does_not_notify_immediately(self):
        plan = self.facade.plan_turn(
            self.handle,
            transcript="плохо голова болит тошнота",
            stt_confidence=0.9,
        )
        self.facade.commit_turn(self.handle, plan, plan.spoken_reply)
        plan = self.facade.plan_turn(
            self.handle,
            transcript="несильная",
            stt_confidence=0.9,
        )
        low = plan.spoken_reply.lower()
        self.assertNotRegex(
            low,
            r"записал.*приложен|родн.*увид|близк.*увид",
            msg=plan.spoken_reply,
        )

    def test_what_after_notify_explains_not_repeats_severity(self):
        plan = self.facade.plan_turn(
            self.handle,
            transcript="плохо голова болит тошнота",
            stt_confidence=0.9,
        )
        self.facade.commit_turn(self.handle, plan, plan.spoken_reply)
        plan = self.facade.plan_turn(
            self.handle,
            transcript="несильная",
            stt_confidence=0.9,
        )
        self.facade.commit_turn(self.handle, plan, plan.spoken_reply)
        plan = self.facade.plan_turn(
            self.handle,
            transcript="утром началось",
            stt_confidence=0.9,
        )
        notify_low = plan.spoken_reply.lower()
        self.assertRegex(
            notify_low,
            r"записал|приложен|родн|близк",
            msg=plan.spoken_reply,
        )
        self.facade.commit_turn(self.handle, plan, plan.spoken_reply)
        plan = self.facade.plan_turn(
            self.handle,
            transcript="Что?",
            stt_confidence=0.9,
        )
        explain_low = plan.spoken_reply.lower()
        self.assertRegex(
            explain_low,
            r"приложен|родн|близк|семь|сохран",
            msg=plan.spoken_reply,
        )
        self.assertNotRegex(
            explain_low,
            r"терпим.*сильн|сильн.*терпим",
            msg=plan.spoken_reply,
        )


if __name__ == "__main__":
    unittest.main()
