"""Per-client phrase memory — the personal layer (pilot only).

Problem: one client's stable phrasing («Колю» = their word) must not leak
into the global model, and another client must never inherit it.

Design:
  - key = (client_id, pending_slot, normalized phrase) — never global
  - a resolution is TRUSTED only after 3 consistent observations; before
    that the turn flows through the normal tiers (anchors → global clf)
  - resolutions: answer (record own words) | skip (advance, no value).
    Garbage is NEVER recorded — debris cannot poison memory.
  - cap 200 entries per client, JSON store, human-readable, deletable
  - client_id "" (unknown) → memory disabled entirely (call-scoped safety)

Learning in process: resolutions confirmed by the global tier with high
confidence (>=0.8) are recorded automatically; trusted after 3 hits.
Rollback: delete the client's file. Audit: file lists every entry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

Resolution = Literal["answer", "skip"]

TRUST_HITS = 3
MAX_ENTRIES = 200

_WS = re.compile(r"\s+")


def _store_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / ".run" / "phrase_memory"


def _norm(text: str) -> str:
    return _WS.sub(" ", (text or "").strip().lower().rstrip(".!?"))[:80]


def _path(client_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", client_id)[:64]
    return _store_dir() / f"{safe}.json"


def _load(client_id: str) -> dict:
    try:
        return json.loads(_path(client_id).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(client_id: str, data: dict) -> None:
    import fcntl

    _store_dir().mkdir(parents=True, exist_ok=True)
    # File lock: concurrent calls of the SAME client must not interleave
    # read-modify-write (pre-scaling fix; SQLite migration when sharded).
    lock_path = _store_dir() / ".lock"
    with open(lock_path, "a+b") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            current: dict = {}
            try:
                current = json.loads(_path(client_id).read_text(encoding="utf-8"))
            except Exception:
                pass
            current.update(data)
            while len(current) > MAX_ENTRIES:
                current.pop(next(iter(current)))
            _path(client_id).write_text(
                json.dumps(current, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        finally:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            except Exception:  # noqa: BLE001
                pass


def resolve(client_id: str, slot: str, text: str) -> Resolution | None:
    """Trusted personal resolution, or None (unknown / untrusted / off)."""
    if not client_id:
        return None
    key = f"{slot} || {_norm(text)}"
    entry = _load(client_id).get(key)
    if not entry or int(entry.get("hits", 0)) < TRUST_HITS:
        return None
    res = entry.get("resolution")
    return res if res in ("answer", "skip") else None


def record(
    client_id: str, slot: str, text: str, resolution: Resolution
) -> None:
    """Learn one confirmed resolution. Garbage must never reach here."""
    if not client_id or resolution not in ("answer", "skip"):
        return
    data = _load(client_id)
    key = f"{slot} || {_norm(text)}"
    entry = data.get(key, {"resolution": resolution, "hits": 0})
    if entry.get("resolution") != resolution:
        # Conflicting evidence — reset trust, keep latest hypothesis untrusted.
        entry = {"resolution": resolution, "hits": 1}
    else:
        entry["hits"] = int(entry.get("hits", 0)) + 1
    data[key] = entry
    while len(data) > MAX_ENTRIES:
        data.pop(next(iter(data)))
    _save(client_id, data)
