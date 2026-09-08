"""Stress gate smoke — fast subset, not full 100-scenario soak."""

from __future__ import annotations

import json
from pathlib import Path

from tools.voice_lab.stress_gate import StressConfig, run_stress_gate


def test_stress_gate_smoke_10(tmp_path: Path) -> None:
    summary = run_stress_gate(
        StressConfig(
            count=10,
            workers=4,
            call_actor_concurrency=2,
            layers="all",
            out_dir=tmp_path / "stress",
            verbose_failures=False,
        )
    )
    assert summary.layers
    assert (tmp_path / "stress" / "summary.json").is_file()
    assert (tmp_path / "stress" / "scenarios.jsonl").is_file()
    payload = json.loads((tmp_path / "stress" / "summary.json").read_text(encoding="utf-8"))
    assert payload["config"]["count"] == 10
    for layer in summary.layers:
        assert layer.total == 10
        assert layer.gate_passed, f"{layer.layer} failed: {layer.failure_buckets}"
