"""Durable persistence: fail-open dialogue never loses data silently.

SpillingCallRecordStore wraps any CallRecordStore. Every write is tried
against the delegate first; if the delegate raises (DB down), the write is
appended to a local JSONL spool (flush + fsync per row) and an ok=False
result is returned — the call continues, nothing is lost.

replay_spool() re-applies spooled writes in file order once the store is
back. Store-level idempotency (idempotency_key / ON CONFLICT / UPDATE
semantics) makes double replay safe.

Reads pass straight through to the delegate.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.contracts.core import (
    CallObservation,
    CallRecordStore,
    CallResultSnapshot,
    DeliveryStage,
    PersistResult,
)
from packages.contracts.events import CallEvent

_log = logging.getLogger("core.spill")


def _spool_dir() -> Path | None:
    raw = os.environ.get("IMVERA_PERSIST_SPOOL_DIR")
    if not raw:
        return None
    return Path(raw)


def _failed(exc: Exception) -> PersistResult:
    return PersistResult(
        ok=False,
        delivery_stage=DeliveryStage.OBSERVATION_RECEIVED,
        error=str(exc),
    )


class SpillingCallRecordStore(CallRecordStore):
    """Write-through store with a local fsync'd spool as the safety net."""

    def __init__(self, delegate: CallRecordStore, spool_dir: Path | str) -> None:
        self._delegate = delegate
        self._spool_dir = Path(spool_dir)
        self._spool_dir.mkdir(parents=True, exist_ok=True)

    def __getattr__(self, name: str) -> Any:
        # Anything else (get_latest_family_snapshot, ...) delegates.
        return getattr(self._delegate, name)

    def get_call_result(
        self, call_id: str, family_id: str
    ) -> CallResultSnapshot | None:
        return self._delegate.get_call_result(call_id, family_id)

    def get_events(self, call_id: str, family_id: str) -> list:
        return self._delegate.get_events(call_id, family_id)

    def get_call_binding(self, call_id: str) -> dict[str, Any] | None:
        return self._delegate.get_call_binding(call_id)

    def get_call_binding_by_fs_uuid(self, fs_uuid: str) -> dict[str, Any] | None:
        return self._delegate.get_call_binding_by_fs_uuid(fs_uuid)

    def _spill(self, op: str, data: dict[str, Any]) -> None:
        day = datetime.now(UTC).strftime("%Y%m%d")
        path = self._spool_dir / f"spill-{day}.jsonl"
        row = {"ts": datetime.now(UTC).isoformat(), "op": op, "data": data}
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def _write(self, op: str, data: dict[str, Any], call) -> PersistResult:
        try:
            return call()
        except Exception as exc:
            _log.exception("persist %s failed, spilling (call continues)", op)
            try:
                self._spill(op, data)
            except Exception:
                _log.exception("spool write failed for %s", op)
            return _failed(exc)

    def ensure_call(self, call_id: str, family_id: str) -> PersistResult:
        return self._write(
            "ensure_call",
            {"call_id": call_id, "family_id": family_id},
            lambda: self._delegate.ensure_call(call_id, family_id),
        )

    def append_event(self, event: CallEvent, family_id: str) -> PersistResult:
        return self._write(
            "append_event",
            {"event": event.model_dump(mode="json"), "family_id": family_id},
            lambda: self._delegate.append_event(event, family_id),
        )

    def save_observation(
        self, observation: CallObservation, family_id: str
    ) -> PersistResult:
        return self._write(
            "save_observation",
            {"observation": observation.model_dump(mode="json"), "family_id": family_id},
            lambda: self._delegate.save_observation(observation, family_id),
        )

    def finalize_call(self, snapshot: CallResultSnapshot) -> PersistResult:
        return self._write(
            "finalize_call",
            {"snapshot": snapshot.model_dump(mode="json")},
            lambda: self._delegate.finalize_call(snapshot),
        )

    def save_dialogue_snapshot(
        self, snapshot: CallResultSnapshot, family_id: str
    ) -> PersistResult:
        return self._write(
            "save_dialogue_snapshot",
            {
                "snapshot": snapshot.model_dump(mode="json"),
                "family_id": family_id,
            },
            lambda: self._delegate.save_dialogue_snapshot(snapshot, family_id),
        )

    def put_call_binding(self, binding: dict[str, Any]) -> PersistResult:
        return self._write(
            "put_call_binding",
            {"binding": binding},
            lambda: self._delegate.put_call_binding(binding),
        )

    def delete_call_binding(self, call_id: str) -> PersistResult:
        return self._write(
            "delete_call_binding",
            {"call_id": call_id},
            lambda: self._delegate.delete_call_binding(call_id),
        )


def replay_spool(spool_dir: Path | str, store: CallRecordStore) -> dict[str, int]:
    """Re-apply spooled writes in order. Returns counts.

    Poison rows (bad JSON, unknown op, invalid payload) are quarantined
    into `<file>.quarantine.jsonl` and SKIPPED — one bad row never blocks
    other calls' data (P0 G-10). A store failure on a valid row still
    stops the run (store down); the rest waits for the next run.
    Fully replayed files are renamed to *.done.
    """
    spool = Path(spool_dir)
    counts = {"applied": 0, "files_done": 0, "stopped": 0, "quarantined": 0}
    for path in sorted(spool.glob("spill-*.jsonl")):
        rows = path.read_text(encoding="utf-8").splitlines()
        ok = True
        for line in rows:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                op, data = row["op"], row["data"]
            except (json.JSONDecodeError, KeyError, TypeError):
                _quarantine(path, line, "unparseable")
                counts["quarantined"] += 1
                continue
            try:
                _apply_row(store, op, data)
            except ValueError as exc:
                # Unknown op / invalid payload: never retryable.
                _log.exception("replay quarantined row in %s", path.name)
                _quarantine(path, line, str(exc))
                counts["quarantined"] += 1
                continue
            except Exception:
                _log.exception("replay stopped at %s row", path.name)
                counts["stopped"] += 1
                ok = False
                break
            counts["applied"] += 1
        if ok:
            path.rename(path.with_suffix(".jsonl.done"))
            counts["files_done"] += 1
    return counts


def _quarantine(path: Path, line: str, reason: str) -> None:
    with path.with_suffix(".jsonl.quarantine").open(
        "a", encoding="utf-8"
    ) as fh:
        fh.write(json.dumps({"reason": reason, "row": line}) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _apply_row(store: CallRecordStore, op: str, data: dict[str, Any]) -> None:
    family_id = data.get("family_id", "")
    if op == "ensure_call":
        store.ensure_call(data["call_id"], family_id)
    elif op == "append_event":
        store.append_event(CallEvent.model_validate(data["event"]), family_id)
    elif op == "save_observation":
        store.save_observation(
            CallObservation.model_validate(data["observation"]), family_id
        )
    elif op == "finalize_call":
        store.finalize_call(CallResultSnapshot.model_validate(data["snapshot"]))
    elif op == "save_dialogue_snapshot":
        store.save_dialogue_snapshot(
            CallResultSnapshot.model_validate(data["snapshot"]), family_id
        )
    elif op == "put_call_binding":
        store.put_call_binding(data["binding"])
    elif op == "delete_call_binding":
        store.delete_call_binding(data["call_id"])
    else:
        raise ValueError(f"unknown spool op {op!r}")
