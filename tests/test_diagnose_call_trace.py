"""diagnose_call_trace.py regression on known failure patterns."""

from __future__ import annotations

import io
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path

from scripts.diagnose_call_trace import diagnose

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "traces"
TRACES = Path(__file__).resolve().parents[1] / ".run" / "traces"


def _run_diagnose(call_id: str) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = diagnose(call_id)
    assert code == 0
    return buf.getvalue()


def test_diagnose_stuck_mute_fixture(tmp_path: Path) -> None:
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    shutil.copy(FIXTURES / "sip-stuck-mute.jsonl", trace_dir / "sip-stuck-mute-fixture.jsonl")
    orig = TRACES
    import scripts.diagnose_call_trace as mod

    mod.TRACES = trace_dir
    try:
        out = _run_diagnose("sip-stuck-mute-fixture")
    finally:
        mod.TRACES = orig
    assert "FAIL: playback.completed but NO listen.enabled" in out


def test_diagnose_deaf_vad_fixture(tmp_path: Path) -> None:
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    shutil.copy(FIXTURES / "sip-deaf-vad.jsonl", trace_dir / "sip-deaf-vad-fixture.jsonl")
    import scripts.diagnose_call_trace as mod

    orig = TRACES
    mod.TRACES = trace_dir
    try:
        out = _run_diagnose("sip-deaf-vad-fixture")
    finally:
        mod.TRACES = orig
    assert "OK: listen.enabled present" in out
    assert "WARN: listen.enabled but no speech" in out
    assert "capture.summary" in out
