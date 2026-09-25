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
