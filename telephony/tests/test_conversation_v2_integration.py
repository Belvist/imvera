"""Orchestrator ↔ ConversationFacade integration (facade-only)."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from conversation_system.domain.api import TurnPlanV2
from core.call_mirror import CallMirror
from core.conversation_v2_bridge import (
    begin_v2_call,
    commit_turn_for_call,
    plan_turn_for_call,
    turn_plan_to_legacy,
)
from core.orchestrator import Serve


def _serve():
    class _Args:
        refs = []
        tts_port_file = None
        tts_port = None
        inference_steps = 6
        no_style = False
        outdir = "/tmp/mossvoice_v2_integration"
        tts_host = None

    os.environ["MOSS_NO_WARMUP"] = "1"
    return Serve(_Args())


class TurnPlanShimTests(unittest.TestCase):
    def test_turn_plan_to_legacy_scripted(self):
        plan = TurnPlanV2(
            user_text="хорошо",
            spoken_reply="Рада слышать. Как настроение?",
            stream=False,
            terminal=False,
            verdict="ok",
            safety_status="ok",
        )
        leg = turn_plan_to_legacy(plan)
        self.assertTrue(leg["scripted"])
        self.assertEqual(leg["fallback"], plan.spoken_reply)
        self.assertFalse(leg["allow_llm"])


class OrchestratorFacadeIntegrationTests(unittest.TestCase):
    def setUp(self):
        os.environ["MOSS_NO_WARMUP"] = "1"

    def test_new_call_returns_facade_greeting(self):
        serve = _serve()
        cid = serve.new_call()
        greeting = serve.call_greeting(cid)
        self.assertTrue(greeting)
        low = greeting.lower()
        self.assertTrue(
            "имвера" in low or "вера" in low,
            msg=greeting,
        )
        self.assertTrue(
            "чувствуете" in low or "поживаете" in low,
            msg=greeting,
        )
        ctx = serve.get_call(cid)
        self.assertIsNotNone(ctx.dialogue_state.get("conversation_v2"))

    def test_plan_turn_wellness_path(self):
        serve = _serve()
        cid = serve.new_call()
        ctx = serve.get_call(cid)
        plan, spoke_v2 = plan_turn_for_call(
            ctx, ctx.agent, transcript="всё хорошо", stt_confidence=0.9)
        self.assertTrue(spoke_v2)
        self.assertTrue(plan.get("v2"))
        self.assertTrue(plan.get("fallback"))

    def test_end_call_facade_summary(self):
        serve = _serve()
        cid = serve.new_call()
        ctx = serve.get_call(cid)
        plan, spoke_v2 = plan_turn_for_call(
            ctx, ctx.agent, transcript="хорошо", stt_confidence=0.9)
        commit_turn_for_call(
            ctx, ctx.agent, plan, plan["fallback"], spoke_via_v2=spoke_v2)
        result = serve.end_call(cid)
        self.assertTrue(result.get("finished"))
        self.assertIn("outcome", result)


class CallMirrorTests(unittest.TestCase):
    def test_outcome_shape(self):
        m = CallMirror()
        m.status = "ok"
        m.notes.append("обсуждено: сон")
        self.assertEqual(m.outcome["status"], "ok")
        self.assertIn("сон", m.outcome["notes"][0])

    def test_llm_timeout_env_override(self):
        from core import call_mirror as cm

        saved = os.environ.get("MOSS_LLM_TIMEOUT_S")
        try:
            os.environ["MOSS_LLM_TIMEOUT_S"] = "5.5"
            self.assertEqual(cm._llm_timeout_s(), 5.5)
            os.environ.pop("MOSS_LLM_TIMEOUT_S", None)
            self.assertEqual(cm._llm_timeout_s(), 8.0)
        finally:
            if saved is None:
                os.environ.pop("MOSS_LLM_TIMEOUT_S", None)
            else:
                os.environ["MOSS_LLM_TIMEOUT_S"] = saved


if __name__ == "__main__":
    unittest.main()
