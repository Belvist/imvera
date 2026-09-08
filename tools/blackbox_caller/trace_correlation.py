"""Correlate black-box SIP call with server-side trace (secondary evidence)."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE_DIR = ROOT / ".run" / "traces"
FORENSIC_DIR = ROOT / ".run" / "freeswitch-forensic"


def find_server_trace(*, since_ts: float, sip_call_id: str | None = None) -> Path | None:
    """Pick newest fs-* trace created after call start."""
    candidates: list[tuple[float, Path]] = []
    if not TRACE_DIR.is_dir():
        return None
    for path in TRACE_DIR.glob("fs-*.jsonl"):
        if path.stat().st_mtime >= since_ts - 1.0:
            candidates.append((path.stat().st_mtime, path))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    chosen = candidates[-1][1]
    if sip_call_id:
        text = chosen.read_text(encoding="utf-8", errors="replace")
        if sip_call_id not in text and len(candidates) > 1:
            return candidates[-2][1]
    return chosen


def copy_server_trace(src: Path, dest: Path) -> None:
    shutil.copy2(src, dest)


def server_trace_summary(trace_path: Path) -> dict:
    rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    types = [row.get("type") for row in rows]
    stt_texts = [
        str(row.get("payload", {}).get("text", ""))
        for row in rows
        if row.get("type") == "stt.final"
    ]
    engine_decisions = [
        row.get("payload", {})
        for row in rows
        if row.get("type") == "stage.timing"
        and row.get("payload", {}).get("stage") == "dialogue.engine_decision"
    ]
    planner = sum(
        1
        for row in rows
        if row.get("type") == "stage.timing"
        and row.get("payload", {}).get("stage") == "dialogue.planner_decision"
        and not row.get("payload", {}).get("skip_planner", True)
    )
    return {
        "event_count": len(rows),
        "stt_final_count": len(stt_texts),
        "stt_texts": stt_texts,
        "engine_decisions": engine_decisions,
        "planner_legacy_events": planner,
        "has_summary_tts": any(
            row.get("type") == "stage.timing" and row.get("payload", {}).get("stage") == "tts.start"
            for row in rows
        ),
    }


def wait_for_trace(since_ts: float, timeout_s: float = 30.0) -> Path | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        found = find_server_trace(since_ts=since_ts)
        if found is not None:
            return found
        time.sleep(0.2)
    return None
