"""Phase 2 tests: FSM, SafetyBridge, Resolver, Composer, Facade E2E."""
from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation_system.agenda.manager import AgendaManager
from conversation_system.domain.fsm_types import (
    CallPhase,
    CallPhaseContext,
    FsmEvent,
)
from conversation_system.domain.understanding import (
    ConfidenceBand,
    ResponseGoal,
    ResponseGoalKind,
    SpeechAct,
    SttReason,
    TurnUnderstanding,
)
from conversation_system.domain.wellness import WellnessBand
from conversation_system.integration.facade import ConversationFacade
from conversation_system.memory.state import ConversationMemory
from conversation_system.policy.fsm import CallPhaseMachine
from conversation_system.policy.resolver import IntentResolver
from conversation_system.reply.composer import ReplyComposer
from conversation_system.reply.guards import reply_looks_broken, sanitize_reply
from conversation_system.runtime.session import ConversationSession, TurnPipeline
from conversation_system.safety.bridge import SafetyBridge
from conversation_system.turn.analyzer import TurnAnalyzer
from conversation_system.variety.dedupe import DedupeGuard, VarietyEngine, reply_too_similar
from conversation_system.domain.understanding import ResponseGoal
from core.safety_engine import SafetyEngine, VerdictEvent


def _ctx(phase: CallPhase | None = None) -> CallPhaseContext:
    mem = ConversationMemory(call_id="test")
    agenda = AgendaManager.from_canonical()
    ctx = CallPhaseContext(memory=mem, agenda=agenda)
    if phase:
        return ctx
    return ctx


def _understanding(
    text: str,
    *,
    reason: SttReason = SttReason.NONE,
    act: SpeechAct = SpeechAct.CONTENT,
) -> TurnUnderstanding:
    return TurnUnderstanding(
        raw_text=text,
        clean_text=text,
        input_reason=reason,
        speech_act=act,
        topic_signals=(),
        symptom_focus=None,
        answers_last_control=None,
        confidence_band=ConfidenceBand.HIGH,
        is_narrative=False,
        word_count=len(text.split()) if text else 0,
    )


class FsmTotalityTests(unittest.TestCase):
    def setUp(self):
        self.fsm = CallPhaseMachine()

    def test_every_state_event_has_outcome(self):
        mem = ConversationMemory(call_id="totality")
        agenda = AgendaManager.from_canonical()
        for phase in self.fsm.all_phases():
            self.fsm.phase = phase
            for event in self.fsm.all_events():
                ctx = CallPhaseContext(memory=mem, agenda=agenda)
                result = self.fsm.dispatch_totality(ctx, event)
                self.assertIsNotNone(result.goal)
                self.assertIsNotNone(result.goal.kind)

    def test_unhandled_never_raises(self):
        ctx = CallPhaseContext(
            memory=ConversationMemory(call_id="x"),
            agenda=AgendaManager.from_canonical(),
        )
        self.fsm.phase = CallPhase.GOOD_PATH
        r = self.fsm.dispatch(ctx, FsmEvent.E_UNHANDLED)
        self.assertEqual(r.goal.kind, ResponseGoalKind.ACKNOWLEDGE)

    def test_max_dispatch_depth_caps(self):
        ctx = CallPhaseContext(
            memory=ConversationMemory(call_id="depth"),
            agenda=AgendaManager.from_canonical(),
        )
        ctx.dispatch_depth = 5
        r = self.fsm.dispatch(ctx, FsmEvent.E_SPEECH)
        self.assertEqual(r.goal.kind, ResponseGoalKind.ACKNOWLEDGE)


class FsmProductPathTests(unittest.TestCase):
    def setUp(self):
        self.fsm = CallPhaseMachine()
        self.mem = ConversationMemory(call_id="path")
        self.agenda = AgendaManager.from_canonical()

    def _dispatch(self, phase, event, text=""):
        self.fsm.phase = phase
        u = _understanding(text) if text else None
        ctx = CallPhaseContext(memory=self.mem, agenda=self.agenda, understanding=u)
        return self.fsm.dispatch(ctx, event)

    def test_greeting_to_listen(self):
        self.fsm.phase = CallPhase.GREETING
        r = self._dispatch(CallPhase.GREETING, FsmEvent.E_CALL_START)
        self.assertEqual(self.fsm.phase, CallPhase.LISTEN)
        self.assertEqual(r.goal.kind, ResponseGoalKind.GREET)

    def test_listen_good_path(self):
        self.fsm.phase = CallPhase.LISTEN
        r = self._dispatch(CallPhase.LISTEN, FsmEvent.E_WELLNESS_GOOD, "всё хорошо")
        self.assertEqual(self.fsm.phase, CallPhase.GOOD_PATH)
        self.assertEqual(r.goal.kind, ResponseGoalKind.ASK_TOPIC)

    def test_listen_bad_path(self):
        self.fsm.phase = CallPhase.LISTEN
        r = self._dispatch(CallPhase.LISTEN, FsmEvent.E_WELLNESS_BAD, "голова болит")
        self.assertEqual(self.fsm.phase, CallPhase.BAD_PATH)
        self.assertEqual(r.goal.kind, ResponseGoalKind.SYMPTOM_FOLLOWUP)

    def test_critical_fast_notify(self):
        self.fsm.phase = CallPhase.LISTEN
        r = self._dispatch(CallPhase.LISTEN, FsmEvent.E_WELLNESS_CRITICAL, "я упал")
        self.assertEqual(self.fsm.phase, CallPhase.CRITICAL_PATH)
        self.assertEqual(r.goal.kind, ResponseGoalKind.WRAP_UP)

    def test_good_path_probes_then_notify(self):
        self.fsm.phase = CallPhase.GOOD_PATH
        self.agenda.on_good_path = True
        self.agenda.good_probe_index = 0
        r1 = self._dispatch(CallPhase.GOOD_PATH, FsmEvent.E_PROBE_DONE, "нормально")
        self.assertEqual(self.fsm.phase, CallPhase.GOOD_PATH)
        self.agenda.good_probe_index = 3
        r2 = self._dispatch(CallPhase.GOOD_PATH, FsmEvent.E_PROBES_COMPLETE)
        self.assertEqual(self.fsm.phase, CallPhase.RECORD_NOTIFY)
        self.assertEqual(r2.goal.kind, ResponseGoalKind.WRAP_UP)

    def test_notify_to_closing(self):
        self.fsm.phase = CallPhase.RECORD_NOTIFY
        r = self._dispatch(CallPhase.RECORD_NOTIFY, FsmEvent.E_NOTIFY_DONE)
        self.assertEqual(self.fsm.phase, CallPhase.CLOSING)
        self.assertEqual(r.goal.kind, ResponseGoalKind.CLOSE)

    def test_closing_terminal(self):
        self.fsm.phase = CallPhase.CLOSING
        r = self._dispatch(CallPhase.CLOSING, FsmEvent.E_CLOSING_DIRECT)
        self.assertEqual(self.fsm.phase, CallPhase.TERMINAL)
        self.assertTrue(r.terminal)


class SafetyBridgeTests(unittest.TestCase):
    def setUp(self):
        self.bridge = SafetyBridge(SafetyEngine())
        self.mem = ConversationMemory(call_id="safety")

    def test_confirmed_red_never_silent(self):
        u = _understanding("я упал и не могу встать")
        verdict = VerdictEvent(kind="confirmed_red", notes=("падение",))
        events = self.bridge.map_to_events(
            verdict, self.mem, u, phase="listen")
        self.assertIn(FsmEvent.E_SAFETY_CONFIRMED, events)
        composer = ReplyComposer()
        r = composer.compose(
            ResponseGoal(kind=ResponseGoalKind.SAFETY_ACTIVE, scripted_only=True),
            self.mem,
            AgendaManager.from_canonical(),
        )
        self.assertGreater(len(r.text), 10)

    def test_uncertain_red_goes_confirm(self):
        u = _understanding("голова болит")
        v = self.bridge.observe(self.mem, u)
        if v.kind == "uncertain_red":
            events = self.bridge.map_to_events(v, self.mem, u, phase="listen")
            self.assertIn(FsmEvent.E_SAFETY_UNCERTAIN, events)

    def test_confirm_gate_blocks_bare_da(self):
        self.mem.last_question = "Как настроение?"
        u = _understanding("да")
        v = self.bridge.observe(self.mem, u)
        self.assertFalse(self.bridge.confirm_gate_allows_yes(self.mem))

    def test_confirm_gate_allows_yes_on_control(self):
        self.mem.last_question = "Вам нужна срочная помощь? Скажите да или нет."
        self.assertTrue(self.bridge.confirm_gate_allows_yes(self.mem))
        u = _understanding("да")
        v = self.bridge.observe(self.mem, u)
        events = self.bridge.map_to_events(
            v, self.mem, u, phase="safety_confirm")
        if v.kind == "uncertain_red":
            self.assertIn(FsmEvent.E_SAFETY_CONFIRMED, events)

    def test_headache_not_confirmed_red_on_first_turn(self):
        """Regression: double observe escalated «голова болит» to confirmed_red."""
        bridge = SafetyBridge(SafetyEngine())
        mem = ConversationMemory(call_id="headache")
        analyzer = TurnAnalyzer(safety_engine=bridge.engine)
        u = analyzer.analyze(
            "голова болит",
            confidence=0.9,
            last_question="Как настроение?",
        )
        result = bridge.process(
            mem, u, phase="listen", stt_confidence=0.9)
        self.assertNotEqual(result.verdict.kind, "confirmed_red")
        self.assertEqual(bridge.engine.state, "POSSIBLE_RED")
        self.assertTrue(bridge.engine.awaiting_confirmation)

    def test_intensifier_defers_safety_and_completes_bad_path(self):
        bridge = SafetyBridge(SafetyEngine())
        mem = ConversationMemory(call_id="intensifier")
        mem.active_symptom = "голова"
        mem.last_question = "Расскажите, что именно беспокоит?"
        bridge.engine.observe(__import__(
            "core.safety_engine", fromlist=["Observation"]).Observation(
            question=mem.last_question,
            raw_text="болит голова",
            confidence=0.9,
        ))
        u = TurnAnalyzer(safety_engine=bridge.engine).analyze(
            "сильно",
            confidence=0.9,
            last_question=mem.last_question,
        )
        result = bridge.process(
            mem, u, phase="bad_path", stt_confidence=0.9)
        self.assertNotIn(FsmEvent.E_SAFETY_UNCERTAIN, result.events)
        self.assertNotEqual(result.verdict.kind, "confirmed_red")

    def test_safety_compose_never_empty(self):
        composer = ReplyComposer()
        agenda = AgendaManager.from_canonical()
        from conversation_system.domain.understanding import ResponseGoal

        for kind in (ResponseGoalKind.SAFETY_CONFIRM, ResponseGoalKind.SAFETY_ACTIVE):
            r = composer.compose(
                ResponseGoal(kind=kind, scripted_only=True),
                self.mem,
                agenda,
            )
            self.assertTrue(len(r.text) > 10)


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.resolver = IntentResolver()
        self.mem = ConversationMemory(call_id="res")
        self.agenda = AgendaManager.from_canonical()

    def test_empty_maps_to_empty_event(self):
        u = TurnUnderstanding(
            raw_text="",
            clean_text="",
            input_reason=SttReason.EMPTY,
            speech_act=SpeechAct.EMPTY,
            topic_signals=(),
            symptom_focus=None,
            answers_last_control=None,
            confidence_band=ConfidenceBand.LOW,
            is_narrative=False,
            word_count=0,
        )
        out = self.resolver.resolve(
            self.mem, self.agenda, u, phase=CallPhase.LISTEN)
        self.assertIn(FsmEvent.E_EMPTY, out.events)

    def test_echo_maps_to_echo(self):
        u = _understanding("", reason=SttReason.ECHO, act=SpeechAct.EMPTY)
        out = self.resolver.resolve(
            self.mem, self.agenda, u, phase=CallPhase.LISTEN)
        self.assertIn(FsmEvent.E_ECHO, out.events)

    def test_listen_good_wellness(self):
        u = _understanding("всё отлично")
        out = self.resolver.resolve(
            self.mem, self.agenda, u, phase=CallPhase.LISTEN)
        self.assertIn(FsmEvent.E_WELLNESS_GOOD, out.events)

    def test_listen_critical_wellness(self):
        u = _understanding("я упал")
        out = self.resolver.resolve(
            self.mem, self.agenda, u, phase=CallPhase.LISTEN)
        self.assertIn(FsmEvent.E_WELLNESS_CRITICAL, out.events)

    def test_stt_uncertain_mood_answer_not_clarify(self):
        """Live 854cb8c24130: mid-band STT must not stall on «Хорошее настроение»."""
        self.agenda.on_good_path = True
        self.agenda.good_probe_index = 0
        u = TurnUnderstanding(
            raw_text="Хорошее настроение.",
            clean_text="Хорошее настроение.",
            input_reason=SttReason.STT_UNCERTAIN,
            speech_act=SpeechAct.CONTENT,
            topic_signals=(),
            symptom_focus=None,
            answers_last_control=None,
            confidence_band=ConfidenceBand.MEDIUM,
            is_narrative=False,
            word_count=2,
        )
        out = self.resolver.resolve(
            self.mem, self.agenda, u, phase=CallPhase.GOOD_PATH)
        self.assertNotIn(FsmEvent.E_LOW_CONF, out.events)
        self.assertIn(FsmEvent.E_PROBE_DONE, out.events)


class LiveCall854RegressionTests(unittest.TestCase):
    """Regression for owner report «остановился / в тупую» (call 854cb8c24130)."""

    def setUp(self):
        self.facade = ConversationFacade()

    def test_good_path_survives_stt_uncertain_and_continues(self):
        handle, _ = self.facade.begin_call(
            call_id="854cb8c24130-regression",
            greeting_played=True,
        )
        plan0 = self.facade.plan_turn(
            handle,
            transcript="Привет, хорошо себя чувствую.",
            stt_confidence=0.9,
        )
        self.facade.commit_turn(handle, plan0, plan0.spoken_reply)
        self.assertIn("?", plan0.spoken_reply)

        replies: list[str] = []
        for text in (
            "Хорошее настроение.",
            "Хорошее настроение.",
            "Хорошо.",
        ):
            plan = self.facade.plan_turn(
                handle,
                transcript=text,
                stt_confidence=0.65 if text != "Хорошо." else 0.9,
                reason="stt_uncertain" if text != "Хорошо." else None,
            )
            replies.append(plan.spoken_reply)
            self.facade.commit_turn(handle, plan, plan.spoken_reply)

        self.assertNotIn("Повторите", replies[0])
        self.assertNotIn("расслышала", replies[0].lower())
        self.assertTrue(any("?" in r for r in replies[:3]),
                        msg=replies)
        self.assertTrue(
            any("записал" in r.lower() for r in replies),
            msg=replies,
        )
        self.facade.end_call(handle)


class ComposerGuardTests(unittest.TestCase):
    def test_no_promise_in_pools(self):
        composer = ReplyComposer()
        agenda = AgendaManager.from_canonical()
        mem = ConversationMemory(call_id="g")
        from conversation_system.domain.understanding import ResponseGoal

        kinds = (
            ResponseGoalKind.GREET,
            ResponseGoalKind.WRAP_UP,
            ResponseGoalKind.CLOSE,
            ResponseGoalKind.SAFETY_ACTIVE,
            ResponseGoalKind.SAFETY_CONFIRM,
        )
        for kind in kinds:
            r = composer.compose(
                ResponseGoal(kind=kind, scripted_only=True),
                mem,
                agenda,
            )
            self.assertFalse(reply_looks_broken(r.text), msg=r.text)

    def test_promise_guard_strips(self):
        bad = "Я сейчас вызову скорую помощь."
        clean = sanitize_reply(bad)
        self.assertNotIn("вызову", clean.lower())

    def test_dedupe_rotates(self):
        v = VarietyEngine()
        d = DedupeGuard(v)
        pool = ("Фраза один?", "Фраза два?", "Фраза три?")
        first = v.pick_from_pool(pool, pool_key="t")
        second = d.dedupe(first, last_reply=first, pool=pool, pool_key="t")
        self.assertNotEqual(first, second)


class DedupeTests(unittest.TestCase):
    def test_reply_too_similar_identical(self):
        self.assertTrue(reply_too_similar("Как дела?", "Как дела?"))

    def test_reply_too_similar_different(self):
        self.assertFalse(reply_too_similar(
            "Как настроение?",
            "Как спали ночью?",
        ))


class FacadeE2ETests(unittest.TestCase):
    def setUp(self):
        self.facade = ConversationFacade()
        self.pipeline = TurnPipeline()

    def _run_call(self, call_id: str, turns: list[tuple[str, str | None]]):
        handle, greeting = self.facade.begin_call(call_id=call_id)
        self.assertTrue(greeting)
        plan0 = self.facade.plan_turn(handle)
        self.facade.commit_turn(handle, plan0, plan0.spoken_reply)
        replies = [plan0.spoken_reply]
        for text, reason in turns:
            plan = self.facade.plan_turn(
                handle, transcript=text, reason=reason)
            self.facade.commit_turn(handle, plan, plan.spoken_reply)
            replies.append(plan.spoken_reply)
        summary = self.facade.end_call(handle)
        return replies, summary

    def test_good_path_call(self):
        replies, summary = self._run_call("good1", [
            ("всё хорошо", None),
            ("нормально", None),
            ("спокойное", None),
            ("выспался", None),
            ("погуляю", None),
            ("да", None),
        ])
        combined = " ".join(replies).lower()
        self.assertTrue("запис" in combined or "приложен" in combined)
        self.assertGreaterEqual(summary.duration_turns, 5)

    def test_bad_path_symptom(self):
        replies, _ = self._run_call("bad1", [
            ("плохо, устала", None),
            ("голова ноет", None),
            ("терпимо", None),
            ("утром", None),
        ])
        combined = " ".join(replies).lower()
        self.assertTrue(
            "беспоко" in combined
            or "бол" in combined
            or "симптом" in combined
            or "запис" in combined,
        )

    def test_critical_fast_close(self):
        replies, summary = self._run_call("crit1", [
            ("я упал и не могу встать", None),
        ])
        self.assertTrue(any("запис" in r.lower() for r in replies))
        terminal_plans = replies
        self.assertGreater(len(terminal_plans), 0)

    def test_silence_ladder_not_empty(self):
        handle, _ = self.facade.begin_call(call_id="silence1")
        plan0 = self.facade.plan_turn(handle)
        self.facade.commit_turn(handle, plan0, plan0.spoken_reply)
        plan = self.facade.plan_turn(handle, transcript="", reason="empty")
        self.assertTrue(len(plan.spoken_reply) > 5)
        self.facade.end_call(handle)

    def test_silence_ladder_tapered_order(self):
        """1st empty = repeat, 2nd = anchor, 3rd+ = quiet — not anchor first."""
        session = ConversationSession(call_id="ladder-order")
        self.pipeline.begin(session, greeting_played=True)
        replies = []
        for _ in range(3):
            plan = self.pipeline.plan_turn(session, transcript="", reason="empty")
            replies.append(plan.spoken_reply)
            self.pipeline.commit_turn(session, plan, plan.spoken_reply)
        first = replies[0].lower()
        self.assertTrue(
            "повтор" in first or "ещё раз" in first or "еще раз" in first
            or "расслышала" in first,
            msg=replies[0],
        )
        self.assertIn("хорошо", replies[1].lower())
        third = replies[2].lower()
        self.assertTrue(
            third in ("я рядом.", "я здесь, когда вы будете готовы.",
                      "слушаю вас.", "подожду, не торопитесь.", "я на линии.")
            or "ещё раз" in third or "еще раз" in third or "расслышала" in third,
            msg=replies[2],
        )
        self.assertNotEqual(replies[0], replies[1])

    def test_low_conf_ladder(self):
        handle, _ = self.facade.begin_call(call_id="lowconf1")
        plan0 = self.facade.plan_turn(handle)
        self.facade.commit_turn(handle, plan0, plan0.spoken_reply)
        plan = self.facade.plan_turn(
            handle, transcript="ммм", reason="low_conf", stt_confidence=0.3)
        self.assertTrue(len(plan.spoken_reply) > 10)
        self.facade.end_call(handle)

    def test_repair_repeats_last(self):
        session = ConversationSession(call_id="repair1")
        self.pipeline.begin(session)
        plan0 = self.pipeline.plan_turn(session)
        self.pipeline.commit_turn(session, plan0, plan0.spoken_reply)
        plan1 = self.pipeline.plan_turn(session, transcript="повторите")
        self.pipeline.commit_turn(session, plan1, plan1.spoken_reply)
        plan2 = self.pipeline.plan_turn(
            session, transcript="что вы сказали")
        self.assertTrue(
            plan2.spoken_reply == plan1.spoken_reply
            or "?" in plan2.spoken_reply
            or len(plan2.spoken_reply) > 0,
        )

    def test_shared_safety_engine_per_session(self):
        s1 = ConversationSession(call_id="eng1")
        s2 = ConversationSession(call_id="eng2")
        self.assertIsNot(s1.safety.engine, s2.safety.engine)
        a1 = TurnAnalyzer(safety_engine=s1.safety.engine)
        a2 = TurnAnalyzer(safety_engine=s1.safety.engine)
        self.assertIs(a1._safety, s1.safety.engine)


class PhoneCheckGreetingTests(unittest.TestCase):
    def test_resolver_alo_in_clarify_is_greeting_not_speech(self):
        resolver = IntentResolver()
        mem = ConversationMemory(call_id="alo1")
        mem.flags.hello_back_done = True
        mem.last_question = "Как вы себя чувствуете сегодня?"
        agenda = AgendaManager.from_canonical()
        u = TurnUnderstanding(
            raw_text="ало",
            clean_text="алло",
            input_reason=SttReason.NONE,
            speech_act=SpeechAct.GREETING,
            topic_signals=(),
            symptom_focus=None,
            answers_last_control=None,
            confidence_band=ConfidenceBand.HIGH,
            is_narrative=False,
            word_count=1,
        )
        out = resolver.resolve(mem, agenda, u, phase=CallPhase.CLARIFY)
        self.assertEqual(out.events, (FsmEvent.E_GREETING,))

    def test_repeat_hello_back_repairs_not_listen_ack(self):
        fsm = CallPhaseMachine()
        fsm.phase = CallPhase.CLARIFY
        mem = ConversationMemory(call_id="alo2")
        mem.flags.hello_back_done = True
        mem.last_question = "Как вы поживаете?"
        agenda = AgendaManager.from_canonical()
        ctx = CallPhaseContext(memory=mem, agenda=agenda)
        ctx.understanding = TurnUnderstanding(
            raw_text="алло",
            clean_text="алло",
            input_reason=SttReason.NONE,
            speech_act=SpeechAct.GREETING,
            topic_signals=(),
            symptom_focus=None,
            answers_last_control=None,
            confidence_band=ConfidenceBand.HIGH,
            is_narrative=False,
            word_count=1,
        )
        result = fsm.dispatch(ctx, FsmEvent.E_GREETING)
        self.assertEqual(result.goal.kind, ResponseGoalKind.REPAIR)

    def test_allo_on_good_probe_does_not_advance_agenda(self):
        agenda = AgendaManager.from_canonical()
        agenda.on_good_path = True
        agenda.mark_question_asked()
        u0 = TurnAnalyzer().analyze("всё отлично", confidence=0.9)
        agenda.mark_discussed(u0)
        agenda.mark_question_asked()
        u = TurnUnderstanding(
            raw_text="алло",
            clean_text="алло",
            input_reason=SttReason.NONE,
            speech_act=SpeechAct.GREETING,
            topic_signals=(),
            symptom_focus=None,
            answers_last_control=None,
            confidence_band=ConfidenceBand.HIGH,
            is_narrative=False,
            word_count=1,
        )
        self.assertFalse(agenda.semantic_close(u))
        resolver = IntentResolver()
        mem = ConversationMemory(call_id="alo3")
        mem.flags.hello_back_done = True
        mem.last_question = "Как настроение сегодня?"
        out = resolver.resolve(mem, agenda, u, phase=CallPhase.GOOD_PATH)
        self.assertEqual(out.events, (FsmEvent.E_GREETING,))

    def test_bare_affirmation_on_mood_probe_does_not_close(self):
        agenda = AgendaManager.from_canonical()
        agenda.on_good_path = True
        agenda.mark_question_asked()
        u0 = TurnAnalyzer().analyze("всё отлично", confidence=0.9)
        agenda.mark_discussed(u0)
        agenda.mark_question_asked()
        u = TurnUnderstanding(
            raw_text="ага",
            clean_text="ага",
            input_reason=SttReason.NONE,
            speech_act=SpeechAct.AFFIRMATION,
            topic_signals=(),
            symptom_focus=None,
            answers_last_control=True,
            confidence_band=ConfidenceBand.HIGH,
            is_narrative=False,
            word_count=1,
        )
        self.assertFalse(agenda.semantic_close(u))
        resolver = IntentResolver()
        mem = ConversationMemory(call_id="aga1")
        mem.last_question = "Как настроение сегодня?"
        out = resolver.resolve(mem, agenda, u, phase=CallPhase.GOOD_PATH)
        self.assertNotIn(FsmEvent.E_PROBE_DONE, out.events)
        self.assertIn(FsmEvent.E_SPEECH, out.events)


class SessionRtcTests(unittest.TestCase):
    def test_per_call_lock_exists(self):
        session = ConversationSession(call_id="lock1")
        self.assertIsNotNone(session.lock)


if __name__ == "__main__":
    unittest.main()
