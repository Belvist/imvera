"""Call recordings as a system — catalog, retention, consent-gated review.

Before this module, recordings were scattered: optional per-utterance WAV
dumps in ``.run/stt_dumps`` (env-gated), per-turn forensic stages, no index,
no retention, no consent metadata, no review tool. This module is the single
owner of recording lifecycle:

- ``finalize_call_entry`` builds one catalog row per call (pure function);
- ``append_catalog`` persists it (best-effort, never raises);
- ``sweep_retention`` deletes audio older than N days, keeps catalog rows;
- ``export_call`` bundles audio + transcript for review, refused without
  recorded consent (explicit override is logged).

CallActor hooks ``note_call_finalized`` after session finalize; observability
never breaks teardown. Pilot retention default (30 days) is an owner
decision point, overridable via ``IMVERA_RECORDINGS_RETENTION_DAYS``.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import time
from pathlib import Path

_log = logging.getLogger("imvera.recordings")

DEFAULT_RETENTION_DAYS = 30


def recordings_dir() -> Path:
    root = os.environ.get("IMVERA_RECORDINGS_DIR", "").strip()
    if root:
        path = Path(root)
    else:
        path = Path(__file__).resolve().parents[2] / ".run" / "recordings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def catalog_path() -> Path:
    return recordings_dir() / "catalog.jsonl"


def audio_glob_for_call(call_id: str) -> list[str]:
    """WAV dumps belonging to a call (stt_dumps layout, env-gated upstream)."""
    base = Path(__file__).resolve().parents[2] / ".run" / "stt_dumps"
    return sorted(glob.glob(str(base / f"{call_id}_*.wav")))


def finalize_call_entry(
    *,
    call_id: str,
    family_id: str = "",
    consent: bool | None = None,
    consent_declined: bool = False,
    termination_reason: str | None = None,
    family_status: str | None = None,
    call_outcome: str | None = None,
    red_flag: bool = False,
    duration_s: float | None = None,
    audio_files: list[str] | None = None,
) -> dict:
    return {
        "call_id": call_id,
        "family_id": family_id,
        "finalized_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "consent": consent,
        "consent_declined": bool(consent_declined),
        "termination_reason": termination_reason,
        "family_status": family_status,
        "call_outcome": call_outcome,
        "red_flag": bool(red_flag),
        "duration_s": duration_s,
        "audio_files": list(audio_files or []),
        "schema": 1,
    }


def append_catalog(entry: dict) -> bool:
    """Best-effort append. Never raises; returns False on failure."""
    try:
        path = catalog_path()
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001 — observability never breaks teardown
        _log.warning("recordings catalog append failed: %s", exc)
        return False


def read_catalog(since: str = "") -> list[dict]:
    path = catalog_path()
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if since and str(row.get("finalized_at", "")) < since:
                    continue
                rows.append(row)
    except OSError as exc:
        _log.warning("recordings catalog read failed: %s", exc)
    return rows


def sweep_retention(
    days: int = DEFAULT_RETENTION_DAYS, roots: list[Path] | None = None
) -> dict[str, int]:
    """Delete audio older than N days. Catalog rows are kept (metadata).
    Never raises; returns counts."""
    cutoff = time.time() - max(days, 0) * 86400.0
    removed = 0
    kept = 0
    scanned = 0
    if roots is None:
        roots = [recordings_dir()]
        stt = Path(__file__).resolve().parents[2] / ".run" / "stt_dumps"
        if stt.exists():
            roots.append(stt)
    for root in roots:
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for path in entries:
            if path.suffix.lower() != ".wav" or not path.is_file():
                continue
            scanned += 1
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
                else:
                    kept += 1
            except OSError:
                continue
    return {"scanned": scanned, "removed": removed, "kept": kept}


def export_call(
    call_id: str,
    out_dir: str | Path,
    *,
    consent_required: bool = True,
    override_reason: str = "",
) -> dict:
    """Bundle a call's audio + transcript for review.

    Refuses without recorded consent unless an explicit override reason is
    given (the override is written into the bundle manifest).
    """
    rows = [r for r in read_catalog() if r.get("call_id") == call_id]
    if not rows:
        return {"ok": False, "error": f"call {call_id} not in catalog"}
    row = rows[-1]
    if consent_required and not row.get("consent"):
        if not override_reason:
            return {
                "ok": False,
                "error": "no recorded consent; pass --override-reason to proceed",
            }
    out = Path(out_dir) / call_id
    out.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for src in row.get("audio_files", []):
        try:
            data = Path(src).read_bytes()
            dst = out / Path(src).name
            dst.write_bytes(data)
            copied.append(dst.name)
        except OSError:
            continue
    manifest = {
        "call_id": call_id,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "catalog_row": row,
        "audio_copied": copied,
        "override_reason": override_reason or None,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return {"ok": True, "dir": str(out), "audio_copied": copied}


def note_call_finalized(session) -> bool:
    """Bridge hook: call after session finalize. Best-effort, never raises."""
    try:
        state = session.state
        snapshot = None
        try:
            snapshot = session.get_persisted_result()
        except Exception:  # noqa: BLE001
            snapshot = None
        outcomes = getattr(snapshot, "outcomes", None)
        checks = getattr(state, "mandatory_checks", {}) or {}
        safety = getattr(session, "safety", None)
        risk = str(getattr(safety, "active_risk", "") or "")
        entry = finalize_call_entry(
            call_id=getattr(state, "call_id", "unknown"),
            family_id=getattr(state, "family_id", ""),
            consent=bool(checks.get("consent", False)) or None,
            consent_declined=bool(getattr(state, "consent_declined", False)),
            termination_reason=str(
                getattr(state, "termination_reason", "") or ""
            )
            or None,
            family_status=getattr(outcomes, "candidate_family_status", None),
            call_outcome=getattr(outcomes, "call_outcome", None),
            red_flag=("RED" in risk.upper()),
            audio_files=audio_glob_for_call(getattr(state, "call_id", "")),
        )
        # Consent proxy note: call consent is the best available signal at
        # finalize; an explicit spoken recording-consent step is a pilot
        # owner decision (see module docstring).
        return append_catalog(entry)
    except Exception as exc:  # noqa: BLE001 — observability never breaks teardown
        _log.warning("recordings finalize hook failed: %s", exc)
        return False
