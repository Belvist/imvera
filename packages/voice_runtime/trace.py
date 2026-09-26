"""Runtime trace — JSONL per call for voice lab diagnostics.

Hot-path safe (P0 plan 3b): record_event() only enqueues (<10us) and a
single daemon thread does the file I/O. flush_traces() drains the queue
(call finalize path). Dropped-event counter on overflow instead of OOM.
IMVERA_TRACE_SYNC=1 restores direct writes (debug only).
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from packages.contracts.runtime import RuntimeEvent

ROOT = Path(__file__).resolve().parents[2]
TRACE_DIR = ROOT / ".run" / "traces"

_MAX_QUEUE = 20000

# ADR-022 tiers. Chatty classes die first under load; errors never do.
# stage.timing dominates live traces (171/222 events on fs-5b509b4f).
CHATTY_TYPES = frozenset({"stage.timing"})
ERROR_SUBSTRINGS = frozenset(
    {"failed", "error", "degraded", "timeout", "cancelled", "TECHNICAL"}
)

# ADR-022 forensic budget (pilot/prod only; debug is unlimited by design):
# after the cap, only errors + the end summary are written.
MAX_FORENSIC_EVENTS = 200
MAX_FORENSIC_BYTES = 64 * 1024

_VALID_MODES = ("debug", "pilot", "prod")


def obs_mode() -> str:
    mode = os.environ.get("IMVERA_OBS_MODE", "debug").strip().lower()
    return mode if mode in _VALID_MODES else "debug"


def keep_event(event_type: str) -> bool:
    """Tier filter (ADR-022). Debug keeps everything (lab default)."""
    mode = obs_mode()
    if mode == "debug":
        return True
    lowered = event_type.lower()
    if any(marker in lowered for marker in ERROR_SUBSTRINGS):
        return True
    if mode == "pilot":
        return event_type not in CHATTY_TYPES
    # prod: errors + turn/call lifecycle only (no per-stage chatter).
    return event_type in {
        "call.started",
        "call.ended",
        "renderer.phrase_ready",
        "stt.final",
        "persistence.committed",
        "persistence.failed",
    }

_log = logging.getLogger("voice.trace")

_queue: queue.Queue = queue.Queue(maxsize=_MAX_QUEUE)
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()
dropped_events = 0
truncated_calls = 0
_call_usage: dict[str, list[int]] = {}
_usage_lock = threading.Lock()


def _write_row(call_id: str, row: dict) -> None:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / f"{call_id}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _worker_loop() -> None:
    while True:
        item = _queue.get()
        if item is None:
            _queue.task_done()
            return
        call_id, row = item
        try:
            _write_row(call_id, row)
        except Exception:
            _log.exception("trace write failed call_id=%s", call_id)
        finally:
            _queue.task_done()


def _ensure_worker() -> None:
    global _worker
    if _worker is not None and _worker.is_alive():
        return
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(
            target=_worker_loop, name="trace-writer", daemon=True
        )
        _worker.start()


def _sync_enabled() -> bool:
    return os.environ.get("IMVERA_TRACE_SYNC") == "1"


def record_event(call_id: str, event: RuntimeEvent) -> None:
    event_type = event.event_type.value
    if not keep_event(event_type):
        return
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "call_id": call_id,
        "type": event_type,
        "payload": event.payload,
    }
    if _sync_enabled():
        _write_row(call_id, row)
        return
    if _over_budget(call_id, event_type, row):
        return
    _ensure_worker()
    global dropped_events
    try:
        _queue.put_nowait((call_id, row))
    except queue.Full:
        dropped_events += 1
        if dropped_events % 100 == 1:
            _log.warning("trace queue full, dropped %d events", dropped_events)


def _is_error_type(event_type: str) -> bool:
    lowered = event_type.lower()
    return any(marker in lowered for marker in ERROR_SUBSTRINGS)


def _over_budget(call_id: str, event_type: str, row: dict) -> bool:
    """Per-call forensic budget (pilot/prod; debug unlimited)."""
    if obs_mode() == "debug" or _is_error_type(event_type):
        return False
    global truncated_calls
    with _usage_lock:
        if len(_call_usage) > 10000:
            _call_usage.clear()
        used = _call_usage.get(call_id)
        if used is None:
            used = [0, 0]
            _call_usage[call_id] = used
        if used[0] < 0:
            return True  # already truncated: errors only from here
        size = len(json.dumps(row, ensure_ascii=False))
        if used[0] >= MAX_FORENSIC_EVENTS or used[1] + size > MAX_FORENSIC_BYTES:
            if used[0] >= 0:
                truncated_calls += 1
                used[0] = -1
                _log.warning("trace budget hit call_id=%s", call_id)
                marker = {
                    "ts": datetime.now(UTC).isoformat(),
                    "call_id": call_id,
                    "type": "trace.truncated",
                    "payload": {"mode": obs_mode()},
                }
                try:
                    _queue.put_nowait((call_id, marker))
                except queue.Full:
                    pass
            return True
        used[0] += 1
        used[1] += size
        return False


def write_call_summary(call_id: str) -> dict:
    """End-of-call summary record (ADR-022 PILOT contract).

    Aggregates the call's own JSONL (turns, actions, errors, stage
    p50/p95) and appends one `call.summary` row. Cheap: single file read.
    """
    path = trace_path(call_id)
    summary: dict = {
        "call_id": call_id,
        "turns": 0,
        "actions": [],
        "errors": [],
        "truncated": False,
        "stage_ms": {},
    }
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    timings: dict[str, list[float]] = {}
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        rtype = str(row.get("type", ""))
        payload = row.get("payload") or {}
        if rtype == "stt.final":
            summary["turns"] += 1
        elif rtype == "renderer.phrase_ready":
            text = str(payload.get("text", ""))[:80]
            if text:
                summary["actions"].append(text)
        elif rtype == "trace.truncated":
            summary["truncated"] = True
        if _is_error_type(rtype):
            summary["errors"].append(rtype)
        if rtype == "stage.timing":
            stage = str(payload.get("stage", "unknown"))
            try:
                timings.setdefault(stage, []).append(float(payload.get("elapsed_ms", 0)))
            except (TypeError, ValueError):
                pass
    for stage, samples in sorted(timings.items()):
        ordered = sorted(samples)
        summary["stage_ms"][stage] = {
            "n": len(ordered),
            "p50": round(ordered[len(ordered) // 2], 1),
            "p95": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 1),
        }
    marker = {
        "ts": datetime.now(UTC).isoformat(),
        "call_id": call_id,
        "type": "call.summary",
        "payload": summary,
    }
    try:
        _write_row(call_id, marker)
    except OSError:
        pass
    with _usage_lock:
        _call_usage.pop(call_id, None)
    return summary


def trace_stats() -> dict[str, int]:
    """Queue depth + drops + truncations for /health (ADR-022: never silent)."""
    return {
        "queued": _queue.qsize(),
        "dropped": dropped_events,
        "truncated_calls": truncated_calls,
    }


def flush_traces(timeout_s: float = 10.0) -> bool:
    """Drain pending writes. Returns True when fully drained."""
    _ensure_worker()
    deadline = time.monotonic() + timeout_s
    while _queue.unfinished_tasks > 0:
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.005)
    return True


def trace_path(call_id: str) -> Path:
    return TRACE_DIR / f"{call_id}.jsonl"


def _flush_at_exit() -> None:
    try:
        flush_traces(timeout_s=5.0)
    except Exception:
        pass


atexit.register(_flush_at_exit)
