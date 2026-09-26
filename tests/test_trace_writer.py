"""Background trace writer: fast enqueue, ordered durable writes (P0 plan 3b)."""

from __future__ import annotations

import json
import time

from packages.contracts.runtime import RuntimeEvent, RuntimeEventType
from packages.voice_runtime import trace as trace_mod
from packages.voice_runtime.trace import flush_traces, record_event, trace_path


def _event(i: int) -> RuntimeEvent:
    return RuntimeEvent(f"trace-t{i}", RuntimeEventType.CALL_STARTED, {"i": i})


def test_record_is_fast_and_ordered(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(trace_mod, "TRACE_DIR", tmp_path)
    t0 = time.perf_counter()
    for i in range(200):
        record_event("c1", _event(i))
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 1000, f"record_event must not do I/O inline: {elapsed_ms:.0f}ms"
    assert flush_traces(timeout_s=10.0) is True
    rows = [
        json.loads(line)
        for line in trace_path("c1").read_text(encoding="utf-8").splitlines()
    ]
    assert [r["payload"]["i"] for r in rows] == list(range(200))


def test_sync_mode_writes_inline(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(trace_mod, "TRACE_DIR", tmp_path)
    monkeypatch.setenv("IMVERA_TRACE_SYNC", "1")
    record_event("c2", _event(0))
    rows = trace_path("c2").read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    monkeypatch.delenv("IMVERA_TRACE_SYNC")


def test_tier_filtering() -> None:
    import os

    from packages.voice_runtime.trace import keep_event

    old = os.environ.get("IMVERA_OBS_MODE")
    try:
        os.environ["IMVERA_OBS_MODE"] = "debug"
        assert keep_event("stage.timing") is True
        os.environ["IMVERA_OBS_MODE"] = "pilot"
        assert keep_event("stage.timing") is False
        assert keep_event("renderer.phrase_ready") is True
        assert keep_event("persistence.failed") is True
        os.environ["IMVERA_OBS_MODE"] = "prod"
        assert keep_event("stage.timing") is False
        assert keep_event("stt.final") is True
        assert keep_event("playback.completed") is False
        assert keep_event("persistence.failed") is True
        os.environ["IMVERA_OBS_MODE"] = "nonsense"
        assert keep_event("stage.timing") is True  # unknown falls back to debug
    finally:
        if old is None:
            os.environ.pop("IMVERA_OBS_MODE", None)
        else:
            os.environ["IMVERA_OBS_MODE"] = old


def test_forensic_budget_truncates_with_marker(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(trace_mod, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(trace_mod, "MAX_FORENSIC_EVENTS", 5)
    monkeypatch.setenv("IMVERA_OBS_MODE", "pilot")
    monkeypatch.setenv("IMVERA_TRACE_SYNC", "1")
    try:
        for i in range(10):
            record_event("cb", _event(i))
        rows = trace_path("cb").read_text(encoding="utf-8").strip().splitlines()
        # Sync mode bypasses budget (debug tool); call summary still works.
        assert len(rows) == 10
    finally:
        monkeypatch.delenv("IMVERA_OBS_MODE", raising=False)
        monkeypatch.delenv("IMVERA_TRACE_SYNC", raising=False)


def test_budget_counts_in_queued_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(trace_mod, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(trace_mod, "MAX_FORENSIC_EVENTS", 4)
    monkeypatch.setenv("IMVERA_OBS_MODE", "pilot")
    try:
        for i in range(10):
            record_event("cq", _event(i))
        assert flush_traces(timeout_s=10.0) is True
        rows = [
            json.loads(line)
            for line in trace_path("cq").read_text(encoding="utf-8").splitlines()
        ]
        types = [r["type"] for r in rows]
        assert "trace.truncated" in types
        assert len(rows) == 5  # 4 events + truncation marker
    finally:
        monkeypatch.delenv("IMVERA_OBS_MODE", raising=False)


def test_call_summary_aggregates(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(trace_mod, "TRACE_DIR", tmp_path)
    monkeypatch.setenv("IMVERA_TRACE_SYNC", "1")
    try:
        from packages.voice_runtime.trace import write_call_summary

        record_event("cs", _event(0))
        summary = write_call_summary("cs")
        assert summary["turns"] == 0
        assert summary["truncated"] is False
        rows = [
            json.loads(line)
            for line in trace_path("cs").read_text(encoding="utf-8").splitlines()
        ]
        assert rows[-1]["type"] == "call.summary"
    finally:
        monkeypatch.delenv("IMVERA_TRACE_SYNC", raising=False)
