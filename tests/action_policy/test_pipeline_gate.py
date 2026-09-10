from __future__ import annotations

from scripts.benchmark_action_policy import run_pipeline_diagnostic


def test_p0_pipeline_diagnostic_has_zero_policy_failures() -> None:
    report = run_pipeline_diagnostic()
    assert report["nlu_state_loss"] == 0
    assert report["policy_failure"] == 0, report["turns"]


def test_fs_77afbbf1_turn2_does_not_repeat_temporal() -> None:
    report = run_pipeline_diagnostic()
    row = next(
        item
        for item in report["turns"]
        if item["fixture"] == "fs-77afbbf1" and item["turn"] == 2
    )
    assert row["chosen"] != "ASK_EPISODE:temporal"
    assert not row["policy_failure"]
