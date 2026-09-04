"""Scenario runner lifecycle and assertion integrity regressions."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from scripts.run_golden_path_scenarios import _check_assertion, run_scenario


class ScenarioRunnerTests(unittest.TestCase):
    def test_padding_turns_after_close_are_not_sent_to_ended_session(self) -> None:
        scenario = {
            "id": "early-close-regression",
            "turns": ["нормально", "до свидания", "это уже после конца"],
            "assertions": [
                {"type": "plan_on_turn", "turn": 2, "action": "CLOSE"},
            ],
        }
        ok, errors = run_scenario(scenario, use_mock=True)
        self.assertTrue(ok, errors)

    def test_plan_assertion_fails_when_turn_was_not_processed(self) -> None:
        error = _check_assertion(
            SimpleNamespace(state=None),
            [],
            {"type": "plan_on_turn", "turn": 3, "action": "CLOSE"},
        )
        self.assertIn("not processed", error or "")

    def test_min_turns_counts_processed_history(self) -> None:
        error = _check_assertion(
            SimpleNamespace(state=None),
            [{"turn": 1}],
            {"type": "min_turns", "count": 2},
        )
        self.assertIn("processed 1", error or "")


if __name__ == "__main__":
    unittest.main()
