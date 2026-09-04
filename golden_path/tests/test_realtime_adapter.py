"""Tests for Golden Path realtime adapter (Track D skeleton)."""
from __future__ import annotations

import unittest

from golden_path.llm import MockLLM
from golden_path.realtime_adapter import GoldenRealtimeAdapter, RealtimeTurn


class RealtimeAdapterTests(unittest.TestCase):
    def test_committed_turn_routes_to_engine(self):
        adapter = GoldenRealtimeAdapter(llm=MockLLM())
        adapter.begin_call("call-1")
        result = adapter.handle_committed_turn(
            RealtimeTurn(
                call_id="call-1",
                text="нормально",
                endpoint_source="tuned_endpoint",
            )
        )
        self.assertGreater(result.turn_no, 0)
        self.assertTrue(result.assistant_text)

    def test_plan_only_does_not_mutate(self):
        adapter = GoldenRealtimeAdapter(llm=MockLLM())
        adapter.begin_call("call-2")
        before = adapter.engine.turn_no
        adapter.plan_committed_turn(
            RealtimeTurn(call_id="call-2", text="хорошо")
        )
        self.assertEqual(adapter.engine.turn_no, before)


if __name__ == "__main__":
    unittest.main()
