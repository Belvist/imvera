"""Tests for Golden Path realtime adapter (Track D skeleton)."""
from __future__ import annotations

import unittest

from golden_path.llm import MockLLM
from golden_path.planner import PlannerAction
from golden_path.realtime_adapter import GoldenRealtimeAdapter, RealtimeTurn
from golden_path.slots import SlotName, SlotStatus


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
        _analysis, preview = adapter.plan_committed_turn(
            RealtimeTurn(call_id="call-2", text="хорошо")
        )
        self.assertEqual(adapter.engine.turn_no, before)
        self.assertEqual(
            adapter.engine.state.slot_statuses[SlotName.WELLNESS],
            SlotStatus.OPEN,
        )
        self.assertEqual(preview.action, PlannerAction.ASK_SLOT)
        self.assertNotEqual(preview.slot, SlotName.WELLNESS)

    def test_plan_only_matches_committed_turn(self):
        adapter = GoldenRealtimeAdapter(llm=MockLLM())
        adapter.begin_call("call-3")
        turn = RealtimeTurn(call_id="call-3", text="нормально")
        _analysis, preview = adapter.plan_committed_turn(turn)
        committed = adapter.handle_committed_turn(turn)
        self.assertEqual(preview, committed.plan)


if __name__ == "__main__":
    unittest.main()
