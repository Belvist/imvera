"""ActionPolicy v8<->v9 differential gate tests (lab harness, no prod changes).

Covers the Step-1 v9 candidate process tool
``tools/voice_lab/policy_diff_v8_v9.py``:
- all ten historical core files run in disposable copies; live bytes stay unchanged
- machine-readable report schema is present and internally consistent
- fs-77afbbf1 probe shows the single expected delta
  (temporal answered -> v9 asks severity)

Session-isolation rule: every variant runs in a disposable CHILD process.
The live worktree is never installed/restored by the evaluator.
In-process file swapping + sys.modules purge would orphan references held by
already-imported test modules (collection imports bind first), breaking
monkeypatch-style tests. Pure helpers (classify/compare) are unit-tested
in-process; everything that touches the working tree runs in a subprocess.

No existing expectations are modified here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.voice_lab import policy_diff_v8_v9 as pdiff

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REASON = pdiff.EXPECTED_REASON
EXPECTED_V9_ACTION = pdiff.EXPECTED_V9_ACTION

ROW_KEYS = {
    "scenario_id",
    "ladder",
    "battery",
    "v8_action",
    "v9_action",
    "same",
    "v8_constraints",
    "v9_constraints",
    "reason_for_difference",
    "snapshot_summary",
    "turn_context",
}

_RESTORE_CHILD_LINES = [
    "import sys",
    "sys.path.insert(0, __ROOT__)",
    "from tools.voice_lab import policy_diff_v8_v9 as pdiff",
    "before = pdiff.snapshot_hashes()",
    "before_bytes = pdiff.read_working_tree()",
    "v8 = {rel: pdiff.git_show_file(pdiff.V8_BASELINE_SHA, rel) for rel in pdiff.POLICY_RELS}",
    "assert len(v8) == 10",
    "with pdiff.isolated_variant(v8) as isolated:",
    "    for rel, data in v8.items(): assert (isolated / rel).read_bytes() == data",
    "    assert pdiff.snapshot_hashes() == before",
    "assert not isolated.exists()",
    "try:",
    "    with pdiff.isolated_variant(v8) as failed:",
    "        raise RuntimeError('probe-exception')",
    "except RuntimeError:",
    "    pass",
    "assert not failed.exists()",
    "assert pdiff.snapshot_hashes() == before",
    "assert pdiff.read_working_tree() == before_bytes",
    "print('RESTORE_OK')",
]


def _run_child(args: list[str], stdin_code: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", *args]
        if stdin_code is None
        else [sys.executable, "-B", "-c", stdin_code],
        capture_output=True,
        check=False,
        cwd=ROOT,
        text=True,
        timeout=300,
    )


def test_v8_baseline_decoupled_from_runtime_pin() -> None:
    """Freeze repin must not move the differential baseline."""
    assert pdiff.V8_BASELINE_SHA == "c0fa158bd2ffb4109d1f0776c3b3245cdff31ce4"
    assert pdiff.V8_BASELINE_SHA.startswith(pdiff.V8_BASELINE_SHORT)
    assert pdiff.FROZEN_POLICY_SHA != pdiff.V8_BASELINE_SHA


def test_evaluator_restores_files_byte_identical() -> None:
    before_hashes = pdiff.snapshot_hashes()
    before_bytes = pdiff.read_working_tree()
    child_code = "\n".join(_RESTORE_CHILD_LINES).replace("__ROOT__", repr(str(ROOT)))
    proc = _run_child([], stdin_code=child_code)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "RESTORE_OK" in proc.stdout
    assert pdiff.snapshot_hashes() == before_hashes
    assert pdiff.read_working_tree() == before_bytes


def _full_report_from_cli() -> tuple[dict, subprocess.CompletedProcess]:
    proc = _run_child(
        ["tools/voice_lab/policy_diff_v8_v9.py", "--stdout-only", "--comparison", "v8-v9"]
    )
    assert proc.returncode in (0, 1), proc.stderr[-2000:]
    return json.loads(proc.stdout), proc


def test_report_schema_present_and_consistent() -> None:
    report, _proc = _full_report_from_cli()
    assert report["files_restored"] is True
    assert report["file_hashes_after"] == report["file_hashes_before"]
    for key in (
        "rows",
        "changed",
        "total_compared",
        "changed_count",
        "expected_count",
        "unexplained_count",
        "gate_pass",
    ):
        assert key in report
    assert report["total_compared"] == len(report["rows"])
    assert report["changed_count"] == len(report["changed"])
    assert report["changed"] == [r for r in report["rows"] if not r["same"]]
    for row in report["rows"]:
        assert ROW_KEYS <= set(row)
        assert row["same"] == (row["v8_action"] == row["v9_action"])
        assert row["reason_for_difference"] in {
            "identical",
            EXPECTED_REASON,
            pdiff.EXPECTED_FRESH_REASON,
            "unexplained",
        }
        if row["same"]:
            assert row["reason_for_difference"] == "identical"


def test_fs77afbbf1_probe_shows_single_expected_delta() -> None:
    report, _proc = _full_report_from_cli()
    ladders = {r["ladder"] for r in report["rows"]}
    assert {"0", "1"} <= ladders
    for ladder in ("0", "1"):
        fixture_rows = [
            r
            for r in report["rows"]
            if r["ladder"] == ladder and r["scenario_id"].startswith("pipeline:fs-77afbbf1:")
        ]
        assert fixture_rows, f"fs-77afbbf1 probe produced no rows (ladder {ladder})"
        changed = [r for r in fixture_rows if not r["same"]]
        assert [r["scenario_id"] for r in changed] == ["pipeline:fs-77afbbf1:turn2"]
        probe = changed[0]
        assert probe["v9_action"] == EXPECTED_V9_ACTION
        assert probe["reason_for_difference"] == EXPECTED_REASON
        summary = probe["snapshot_summary"]
        assert summary["last_question_need"] == "temporal"
        assert summary["temporal_known"] is True
        assert summary["current_known"] is True
        assert summary["severity_known"] is False


def test_gate_passes_with_both_dispositioned_deltas() -> None:
    """Owner disposition: fs-1f6d3000:turn2 is the documented snapshot.py
    fresh-issue probe guard (same intentional commit, distinct reason from the
    temporal retention). Both deltas classified, gate passes, restore intact."""
    report, proc = _full_report_from_cli()
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert report["gate_pass"] is True
    assert report["unexplained_count"] == 0
    fresh = [
        r for r in report["changed"] if r["reason_for_difference"] == pdiff.EXPECTED_FRESH_REASON
    ]
    assert {(r["ladder"], r["scenario_id"]) for r in fresh} == {
        ("0", "pipeline:fs-1f6d3000:turn2"),
        ("1", "pipeline:fs-1f6d3000:turn2"),
    }
    for row in fresh:
        assert row["v9_action"] == EXPECTED_V9_ACTION
        assert row["turn_context"]["has_new_speaker_issue"] is True
        assert row["snapshot_summary"]["severity_known"] is False
        assert row["snapshot_summary"]["active_episode_id"]


def _row(action: str, fresh_issue: bool = False, episode: str | None = None, **summary) -> dict:
    base = {
        "action": action,
        "rejected": [],
        "snapshot_summary": {
            "last_question_need": None,
            "temporal_known": None,
            "current_known": None,
            "severity_known": None,
            "active_episode_id": episode,
        },
        "turn_context": {"has_new_speaker_issue": fresh_issue},
    }
    base["snapshot_summary"].update(summary)
    return base


def test_classify_unit() -> None:
    same = _row("ACK_ONLY")
    assert pdiff.classify(same, dict(same)) == "identical"
    v8 = _row(
        "ACK_ONLY",
        last_question_need="temporal",
        temporal_known=True,
        current_known=True,
        severity_known=False,
    )
    v9 = _row(
        EXPECTED_V9_ACTION,
        last_question_need="temporal",
        temporal_known=True,
        current_known=True,
        severity_known=False,
    )
    assert pdiff.classify(v8, v9) == EXPECTED_REASON
    v9_other = _row(
        "SUMMARY_CLOSE",
        last_question_need="temporal",
        temporal_known=True,
        current_known=True,
        severity_known=False,
    )
    assert pdiff.classify(v8, v9_other) == "unexplained"
    v9_concern = _row(
        EXPECTED_V9_ACTION,
        last_question_need="concern",
        temporal_known=True,
        current_known=True,
        severity_known=False,
    )
    v8_concern = _row(
        "ACK_ONLY",
        last_question_need="concern",
        temporal_known=True,
        current_known=True,
        severity_known=False,
    )
    assert pdiff.classify(v8_concern, v9_concern) == "unexplained"
    v9_fresh = _row(
        EXPECTED_V9_ACTION,
        fresh_issue=True,
        episode="ep-1",
        last_question_need="concern",
        temporal_known=True,
        current_known=True,
        severity_known=False,
    )
    v8_fresh = _row(
        "ACK_ONLY",
        fresh_issue=True,
        episode="ep-1",
        last_question_need="concern",
        temporal_known=True,
        current_known=True,
        severity_known=False,
    )
    assert pdiff.classify(v8_fresh, v9_fresh) == pdiff.EXPECTED_FRESH_REASON
    v9_both = _row(
        EXPECTED_V9_ACTION,
        fresh_issue=True,
        episode="ep-1",
        last_question_need="temporal",
        temporal_known=True,
        current_known=True,
        severity_known=False,
    )
    v8_both = _row(
        "ACK_ONLY",
        fresh_issue=True,
        episode="ep-1",
        last_question_need="temporal",
        temporal_known=True,
        current_known=True,
        severity_known=False,
    )
    assert pdiff.classify(v8_both, v9_both) == EXPECTED_REASON
    v9_no_ep = _row(
        EXPECTED_V9_ACTION, fresh_issue=True, last_question_need="concern", severity_known=False
    )
    v8_no_ep = _row(
        "ACK_ONLY", fresh_issue=True, last_question_need="concern", severity_known=False
    )
    assert pdiff.classify(v8_no_ep, v9_no_ep) == "unexplained"


def test_compare_runs_unit() -> None:
    v8_rows = [
        {
            "ladder": "1",
            "scenario_id": "s1",
            "battery": "snapshot",
            "action": "ACK_ONLY",
            "rejected": [],
            "snapshot_summary": {},
            "turn_context": {},
        },
        {
            "ladder": "1",
            "scenario_id": "s2",
            "battery": "snapshot",
            "action": "ACK_ONLY",
            "rejected": [],
            "snapshot_summary": {},
            "turn_context": {},
        },
    ]
    v9_rows = [
        dict(v8_rows[0]),
        {**v8_rows[1], "action": "SUMMARY_CLOSE"},
    ]
    entries, changed = pdiff.compare_runs(v8_rows, v9_rows)
    assert len(entries) == 2
    assert [e["scenario_id"] for e in changed] == ["s2"]
    assert changed[0]["v8_action"] == "ACK_ONLY"
    assert changed[0]["v9_action"] == "SUMMARY_CLOSE"
    with pytest.raises(RuntimeError, match="battery key mismatch"):
        pdiff.compare_runs(v8_rows, v9_rows[:1])


def test_current_v10_gate_is_isolated_and_only_thread_deltas():
    before = pdiff.snapshot_hashes()
    proc = _run_child(["tools/voice_lab/policy_diff_v8_v9.py", "--stdout-only"])
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["comparison"] == "v9-v10"
    assert report["baseline_policy_version"] == "action-policy-phase1-v9"
    assert report["candidate_policy_version"] == "action-policy-phase1-v10"
    assert report["candidate_sha"] == pdiff.FROZEN_POLICY_SHA
    assert report["working_tree_untouched"] and report["gate_pass"]
    assert report["unexplained_count"] == 0 and not report["failed_expectations"]
    assert len(report["baseline_file_hashes"]) == len(report["candidate_file_hashes"]) == 10
    assert all(
        row["battery"] == "conversation_v10"
        and row["reason_for_difference"] == "expected-user-led-thread-move"
        for row in report["changed"]
    )
    assert before == pdiff.snapshot_hashes()
