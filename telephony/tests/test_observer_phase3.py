"""Phase 3 observer — LLM enricher, supervisor, explicit pending, multi-option CHOICE."""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation_system.domain.pending_question import (
    PendingQuestion,
    PendingQuestionType,
    apply_pending_to_memory,
    infer_pending_from_prompt,
    validate_pending_answer,
)
from conversation_system.domain.understanding import (
    ConfidenceBand,
    SpeechAct,
    SttReason,
    TurnUnderstanding,
)
from conversation_system.memory.state import ConversationMemory
from conversation_system.observer import Observer
from conversation_system.observer.llm_enricher import (
    LlmObserverEnricher,
    _parse_observer_json,
)
from conversation_system.observer.supervisor import ObserverSupervisor
from conversation_system.reply.composer import ReplyComposer
from conversation_system.domain.understanding import ResponseGoal, ResponseGoalKind
from conversation_system.agenda.manager import AgendaManager


def _understanding(text: str, *, act: SpeechAct = SpeechAct.CONTENT) -> TurnUnderstanding:
    return TurnUnderstanding(
        raw_text=text,
        clean_text=text,
        input_reason=SttReason.NONE,
        speech_act=act,
        topic_signals=(),
        symptom_focus=None,
        answers_last_control=None,
        confidence_band=ConfidenceBand.HIGH,
        is_narrative=False,
        word_count=len(text.split()),
    )


class LlmObserverFallbackTests(unittest.TestCase):
    def test_llm_timeout_falls_back_to_deterministic(self):
        class _SlowLlm:
            def chat(self, messages, max_tokens=100, temp=0.65, timeout=15):
                raise TimeoutError("observer timeout")

        mem = ConversationMemory(call_id="llm-fb")
        obs = Observer(_SlowLlm())
        u = _understanding("зачем вы звоните?", act=SpeechAct.QUESTION)
        patch = obs.observe_turn(mem, u)
        self.assertIn("Имвера", patch.next_directive)
        self.assertFalse(patch.llm_enriched)

    def test_llm_invalid_json_falls_back(self):
        class _BadJsonLlm:
            def chat(self, messages, max_tokens=100, temp=0.65, timeout=15):
                return "not json at all"

        mem = ConversationMemory(call_id="llm-json")
        obs = Observer(_BadJsonLlm())
        u = _understanding("голова болит")
        patch = obs.observe_turn(mem, u)
        self.assertFalse(patch.llm_enriched)

    def test_llm_enrichment_merges_facts(self):
        payload = {
            "facts": ["приняла таблетку"],
            "corrections": [],
            "contradictions": [],
            "next_directive_hint": "Уточни как таблетка помогла.",
        }

        class _GoodLlm:
            def chat(self, messages, max_tokens=100, temp=0.65, timeout=15):
                return json.dumps(payload)

        mem = ConversationMemory(call_id="llm-ok")
        obs = Observer(_GoodLlm())
        u = _understanding("таблетку выпила")
        with mock.patch(
            "conversation_system.observer.llm_enricher.observer_llm_blocking_enabled",
            return_value=True,
        ):
            patch = obs.observe_turn(mem, u)
        self.assertTrue(patch.llm_enriched)
        for mp in patch.memory_patches:
            mem.apply(mp)
        self.assertTrue(any("таблет" in f for f in mem.facts))
        self.assertIn("таблетка", patch.next_directive.lower())

    def test_parse_observer_json_strips_markdown_fence(self):
        raw = '```json\n{"facts":[],"corrections":[],"contradictions":[],"next_directive_hint":"ok"}\n```'
        parsed = _parse_observer_json(raw)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.next_directive_hint, "ok")


class SupervisorOverrideTests(unittest.TestCase):
    def test_supervisor_strips_promise_directive(self):
        from conversation_system.observer.observer import ObserverPatch

        mem = ConversationMemory(call_id="sup1")
        base = ObserverPatch(
            next_directive="Ответь на вопрос.",
            llm_enriched=False,
        )
        bad = ObserverPatch(
            next_directive="Я позвоню врачу и уточню.",
            llm_enriched=True,
        )
        sup = ObserverSupervisor()
        out = sup.review(
            bad,
            memory=mem,
            base_patch=base,
            llm_used=True,
        )
        self.assertEqual(out.next_directive, base.next_directive)
        self.assertIn("promise_phrase_in_directive", out.supervisor_overrides)

    def test_supervisor_blocks_agenda_skip_on_invalid_choice(self):
        from conversation_system.observer.observer import ObserverPatch

        mem = ConversationMemory(call_id="sup2")
        base = ObserverPatch(
            next_directive="Переспроси варианты.",
            pending_invalid=True,
        )
        bad = ObserverPatch(
            next_directive="Продолжи следующую тему повестки.",
            pending_invalid=True,
            llm_enriched=True,
        )
        sup = ObserverSupervisor()
        out = sup.review(
            bad,
            memory=mem,
            base_patch=base,
            llm_used=True,
        )
        self.assertEqual(out.next_directive, base.next_directive)
        self.assertIn("agenda_skip_on_invalid_choice", out.supervisor_overrides)

    def test_supervisor_rejects_hallucinated_llm_correction(self):
        from conversation_system.observer.observer import ObserverPatch

        mem = ConversationMemory(call_id="sup3")
        base = ObserverPatch(corrections=())
        bad = ObserverPatch(
            corrections=("просто хороший день",),
            llm_enriched=True,
        )
        sup = ObserverSupervisor()
        out = sup.review(
            bad,
            memory=mem,
            understanding=_understanding("нормально"),
            base_patch=base,
            llm_used=True,
        )
        self.assertEqual(out.corrections, ())
        self.assertIn("llm_correction_rejected", out.supervisor_overrides)


class ExplicitPendingAtComposeTests(unittest.TestCase):
    def test_apply_pending_to_memory_sets_both_layers(self):
        mem = ConversationMemory(call_id="pq1")
        pq = apply_pending_to_memory(
            mem,
            "Болит утром или вечером?",
            turn_no=3,
        )
        self.assertIsNotNone(pq)
        assert pq is not None
        self.assertEqual(pq.kind, PendingQuestionType.CHOICE)
        self.assertIs(mem.pending_question, pq)
        self.assertIs(mem.observer_state.pending_question, pq)

    def test_commit_turn_sets_pending_from_spoken(self):
        from conversation_system.domain.api import TurnPlanV2
        from conversation_system.runtime.session import (
            ConversationSession,
            TurnPipeline,
        )

        session = ConversationSession(call_id="pq2")
        session.greeting_played = True
        session.fsm.phase = __import__(
            "conversation_system.domain.fsm_types",
            fromlist=["CallPhase"],
        ).CallPhase.LISTEN
        spoken = "Как сон — глубокий или беспокойный?"
        plan = TurnPlanV2(
            user_text="нормально",
            spoken_reply="fallback",
            stream=False,
            terminal=False,
            verdict="ok",
            safety_status="ok",
            dialogue_step=1,
        )
        TurnPipeline().commit_turn(session, plan, spoken)
        self.assertIn("?", spoken)
        self.assertIsNotNone(session.memory.pending_question)
        assert session.memory.pending_question is not None
        self.assertEqual(
            session.memory.pending_question.kind,
            PendingQuestionType.CHOICE,
        )
        self.assertEqual(session.memory.last_question, spoken)


class MultiOptionChoiceTests(unittest.TestCase):
    def test_infer_three_way_choice_from_comma_or_list(self):
        pq = infer_pending_from_prompt(
            "Что беспокоит — тяжесть, слабость или что-то другое?")
        self.assertIsNotNone(pq)
        assert pq is not None
        self.assertEqual(pq.kind, PendingQuestionType.CHOICE)
        self.assertGreaterEqual(len(pq.choices), 3)
        self.assertIn("тяжесть", pq.choices)
        self.assertIn("слабость", pq.choices)

    def test_bare_da_still_invalid_on_multi_choice(self):
        pq = infer_pending_from_prompt(
            "Что беспокоит — тяжесть, слабость или что-то другое?")
        assert pq is not None
        valid, reason = validate_pending_answer(pq, "да")
        self.assertFalse(valid)
        self.assertEqual(reason, "choice_needs_pick")

    def test_named_option_accepted_on_multi_choice(self):
        pq = infer_pending_from_prompt(
            "Что беспокоит — тяжесть, слабость или что-то другое?")
        assert pq is not None
        valid, _ = validate_pending_answer(pq, "слабость")
        self.assertTrue(valid)

    def test_binary_choice_still_works(self):
        pq = infer_pending_from_prompt("Болит утром или вечером?")
        assert pq is not None
        self.assertEqual(pq.kind, PendingQuestionType.CHOICE)
        self.assertIn("утром", pq.choices)
        self.assertIn("вечером", pq.choices)


class LlmEnricherUnitTests(unittest.TestCase):
    def test_enricher_returns_none_without_llm(self):
        enricher = LlmObserverEnricher(None)
        mem = ConversationMemory(call_id="no-llm")
        u = _understanding("привет")
        self.assertIsNone(enricher.enrich(mem, u))


if __name__ == "__main__":
    unittest.main()
