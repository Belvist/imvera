from __future__ import annotations

from scripts.benchmark_action_policy import run_pipeline_diagnostic


def test_p0_pipeline_diagnostic_has_zero_policy_failures() -> None:
    report = run_pipeline_diagnostic()
    assert report["nlu_state_loss"] == 0
    assert report["policy_failure"] == 0, report["turns"]
