"""Human-readable call trace on disk — date/time + dialogue without hunting call_id.

Every live call writes under ``{outdir}/{call_id}/``:
  * ``call_meta.json`` — start/end timestamps (MSK), caller_id, paths
  * ``dialogue.txt`` — running transcript with per-turn timestamps

Root ``{outdir}/``:
  * ``calls_journal.jsonl`` — append-only index (grep/tail friendly)
  * ``LATEST_CALL.txt`` — open this file to see the most recent call
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

_MSK = timezone(timedelta(hours=3))
_LOCK = threading.RLock()


def _now_msk() -> tuple[str, str]:
    dt = datetime.now(_MSK)
    return dt.isoformat(timespec="seconds"), dt.strftime("%Y-%m-%d %H:%M:%S MSK")


def _safe_call_id(call_id: str) -> str:
    return (call_id or "unknown").replace("/", "_").replace("..", "")


def _call_dir(outdir: str, call_id: str) -> str:
    return os.path.join(outdir, _safe_call_id(call_id))


def _write_json(path: str, payload: Mapping[str, Any]) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _append_line(path: str, line: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def _journal_append(outdir: str, event: Mapping[str, Any]) -> None:
    path = os.path.join(outdir, "calls_journal.jsonl")
    iso, human = _now_msk()
    row = {"at_iso": iso, "at_human": human, **dict(event)}
    _append_line(path, json.dumps(row, ensure_ascii=False))


def _minio_paths(call_id: str) -> dict[str, str]:
    bucket = os.environ.get("MOSS_S3_BUCKET", "mossvoice-recordings")
    prefix = f"calls/{_safe_call_id(call_id)}/"
    return {
        "minio_bucket": bucket,
        "minio_prefix": prefix,
        "minio_console_url": (
            f"http://127.0.0.1:9001/browser/{bucket}/{prefix}"
        ),
    }


def record_call_start(
    outdir: str,
    call_id: str,
    *,
    caller_id: Optional[str] = None,
    greeting: Optional[str] = None,
) -> str:
    """Create per-call folder metadata and root index entry. Returns call dir."""
    if not outdir or not call_id:
        return ""
    iso, human = _now_msk()
    cdir = _call_dir(outdir, call_id)
    os.makedirs(cdir, mode=0o700, exist_ok=True)

    meta = {
        "call_id": _safe_call_id(call_id),
        "started_at_iso": iso,
        "started_at_human": human,
        "caller_id": (caller_id or "").strip(),
        "call_dir": cdir,
        "greeting": (greeting or "").strip(),
        "turns": [],
        **_minio_paths(call_id),
    }
    with _LOCK:
        _write_json(os.path.join(cdir, "call_meta.json"), meta)
        header = (
            f"Звонок {_safe_call_id(call_id)}\n"
            f"Начало: {human}\n"
            f"Абонент: {caller_id or 'неизвестен'}\n"
            f"Папка: {cdir}\n"
            f"{'=' * 60}\n"
        )
        dialogue_path = os.path.join(cdir, "dialogue.txt")
        with open(dialogue_path, "w", encoding="utf-8") as f:
            f.write(header)
            if greeting:
                f.write(f"[{human}] Вера: {greeting}\n")
        _journal_append(outdir, {
            "event": "call_start",
            "call_id": _safe_call_id(call_id),
            "caller_id": caller_id or "",
            "call_dir": cdir,
        })
        latest = (
            "ПОСЛЕДНИЙ ЗВОНОК (обновляется автоматически)\n"
            "==========================================\n"
            f"Время:   {human}\n"
            f"ID:      {_safe_call_id(call_id)}\n"
            f"Папка:   {cdir}\n"
            f"MinIO:   s3://{meta['minio_bucket']}/{meta['minio_prefix']}\n"
            f"Браузер: {meta['minio_console_url']}\n"
            f"Телефон: {caller_id or 'неизвестен'}\n"
            "\n"
            "Расшифровка: откройте dialogue.txt в папке звонка.\n"
            "Журнал всех звонков: calls_journal.jsonl в этой же папке.\n"
            "\n"
            f"Быстро: tail -5 {os.path.join(outdir, 'calls_journal.jsonl')}\n"
        )
        latest_path = os.path.join(outdir, "LATEST_CALL.txt")
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(latest)
    return cdir


def record_turn(
    outdir: str,
    call_id: str,
    turn_no: int,
    role: str,
    text: str,
    *,
    source: Optional[str] = None,
    confidence: Optional[float] = None,
    input_reason: Optional[str] = None,
    audio_key: Optional[str] = None,
) -> None:
    """Append one dialogue line with timestamp to call folder + journal."""
    if not outdir or not call_id:
        return
    iso, human = _now_msk()
    cdir = _call_dir(outdir, call_id)
    who = "Абонент" if role == "user" else "Вера"
    line = (text or "").strip()
    if not line and role == "user":
        reason = (input_reason or source or "").strip()
        line = f"(пусто{': ' + reason if reason else ''})"
    display = f"[{human}] {who}: {line}"

    with _LOCK:
        os.makedirs(cdir, mode=0o700, exist_ok=True)
        _append_line(os.path.join(cdir, "dialogue.txt"), display)
        meta_path = os.path.join(cdir, "call_meta.json")
        meta: dict[str, Any] = {}
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, OSError):
                meta = {}
        if not meta:
            meta = {"call_id": _safe_call_id(call_id), "call_dir": cdir}
        turns = meta.get("turns")
        if not isinstance(turns, list):
            turns = []
        turns.append({
            "turn_no": turn_no,
            "at_iso": iso,
            "at_human": human,
            "role": role,
            "text": text or "",
            "source": source or "",
            "confidence": confidence,
            "input_reason": input_reason or "",
            "audio_key": audio_key or "",
        })
        meta["turns"] = turns
        meta["last_turn_at_human"] = human
        _write_json(meta_path, meta)
        preview = (line[:120] + "…") if len(line) > 120 else line
        _journal_append(outdir, {
            "event": "turn",
            "call_id": _safe_call_id(call_id),
            "turn_no": turn_no,
            "role": role,
            "preview": preview,
            "source": source or "",
            "input_reason": input_reason or "",
            "minio_key": audio_key or "",
        })


def record_call_end(
    outdir: str,
    call_id: str,
    *,
    status: Optional[str] = None,
    notes: Optional[list] = None,
) -> None:
    """Mark call finished in meta + journal."""
    if not outdir or not call_id:
        return
    iso, human = _now_msk()
    cdir = _call_dir(outdir, call_id)
    with _LOCK:
        meta_path = os.path.join(cdir, "call_meta.json")
        meta: dict[str, Any] = {}
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, OSError):
                meta = {}
        meta["ended_at_iso"] = iso
        meta["ended_at_human"] = human
        meta["status"] = status or ""
        if notes:
            meta["notes"] = list(notes)
        if meta:
            _write_json(meta_path, meta)
        _append_line(
            os.path.join(cdir, "dialogue.txt"),
            f"[{human}] --- конец звонка ({status or 'ok'}) ---",
        )
        _journal_append(outdir, {
            "event": "call_end",
            "call_id": _safe_call_id(call_id),
            "status": status or "",
        })
