"""Runtime trace — JSONL per call for voice lab diagnostics."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from packages.contracts.runtime import RuntimeEvent

ROOT = Path(__file__).resolve().parents[2]
TRACE_DIR = ROOT / ".run" / "traces"


def record_event(call_id: str, event: RuntimeEvent) -> None:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / f"{call_id}.jsonl"
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "call_id": call_id,
        "type": event.event_type.value,
        "payload": event.payload,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def trace_path(call_id: str) -> Path:
    return TRACE_DIR / f"{call_id}.jsonl"
