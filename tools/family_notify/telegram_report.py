"""Temporary family report to Telegram (demo stand-in for the app).

One file, stdlib only. After a call ends, sends what the app would show:
status color + short summary + key facts. The status is the DIALOGUE
CANDIDATE (voiseup never owns verdicts — Core does); the message says so.

Usage:
    TG_BOT_TOKEN=... TG_CHAT_ID=... python3 tools/family_notify/telegram_report.py --call-id fs-xxxx
    python3 tools/family_notify/telegram_report.py --watch [--interval 30]
    python3 tools/family_notify/telegram_report.py --call-id fs-xxxx --dry-run

Env: IMVERA_TG_BOT_TOKEN, IMVERA_TG_CHAT_ID, IMVERA_PG_URL.
Watch state: .run/family_notify_sent.json (already-sent call ids).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

COLOR = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴", "UNSET": "⚪"}
COLOR_RU = {
    "GREEN": "Всё хорошо",
    "YELLOW": "Нужно внимание",
    "RED": "Тревога",
    "UNSET": "Нет данных",
}
SENT_FILE = _ROOT / ".run" / "family_notify_sent.json"


def _load_sent() -> set[str]:
    try:
        return set(json.loads(SENT_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_sent(sent: set[str]) -> None:
    SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SENT_FILE.write_text(json.dumps(sorted(sent)), encoding="utf-8")


def _snapshot(call_id: str):
    from packages.core import create_call_record_store

    store = create_call_record_store()
    try:
        import psycopg

        dsn = os.environ.get("IMVERA_PG_URL", "")
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT family_id FROM call_results WHERE call_id = %s",
                    (call_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return store.get_call_result(call_id, row[0])
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass


def build_message(call_id: str, snap) -> str:
    d = snap.model_dump(mode="json")
    outcomes = d.get("outcomes") or {}
    status = str(outcomes.get("candidate_family_status") or "UNSET")
    meta = d.get("metadata") or {}
    facts = d.get("facts") or {}
    name = str(meta.get("elder_display_name") or "—")
    concern = str(meta.get("wellness_concern") or "").strip()
    ended = d.get("call_ended")
    when = datetime.now(UTC).astimezone().strftime("%d.%m %H:%M")

    lines = [
        f"{COLOR.get(status, '⚪')} Вера: {COLOR_RU.get(status, status)}",
        f"👵 {name} · звонок {when}",
        "",
    ]
    if concern:
        lines.append(f"Жалоба: {concern}")
    for label, key in (("Самочувствие", "wellness"), ("Настроение", "mood"), ("Сон", "sleep")):
        if facts.get(key):
            lines.append(f"{label}: {facts[key]}")
    meds = (meta.get("observations") if isinstance(meta.get("observations"), dict) else None) or {}
    if isinstance(meds, dict) and meds.get("coverage_medication_today"):
        lines.append(f"Лекарства: {meds['coverage_medication_today']}")
    its = None
    obs = d.get("observations")
    if isinstance(obs, list):
        for o in obs:
            if isinstance(o, dict) and o.get("field") == "important_to_share":
                its = o.get("value")
    if its:
        lines.append(f"Важно: {its}")
    if not ended:
        lines.append("Звонок не завершён штатно.")
    lines += [
        "",
        "Предварительный статус из диалога (демо).",
    ]
    return "\n".join(lines)


def send_message(token: str, chat_id: str, text: str, timeout_s: float = 15.0) -> None:
    body = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text}
    ).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        payload = json.loads(resp.read())
    if not payload.get("ok"):
        raise RuntimeError(f"telegram API error: {payload}")


def report_call(call_id: str, *, dry_run: bool) -> bool:
    snap = _snapshot(call_id)
    if snap is None:
        print(f"no snapshot for {call_id}")
        return False
    text = build_message(call_id, snap)
    if dry_run:
        print(text)
        return True
    token = os.environ.get("IMVERA_TG_BOT_TOKEN", "")
    chat_ids = [
        c.strip()
        for c in os.environ.get("IMVERA_TG_CHAT_ID", "").split(",")
        if c.strip()
    ]
    if not token or not chat_ids:
        print("IMVERA_TG_BOT_TOKEN / IMVERA_TG_CHAT_ID not set — dry output:")
        print(text)
        return False
    failed: list[str] = []
    for chat_id in chat_ids:
        try:
            send_message(token, chat_id, text)
        except Exception as exc:
            # One blocked chat (403) must not kill delivery to the rest.
            print(f"send failed chat_id={chat_id}: {exc}")
            failed.append(chat_id)
    delivered = len(chat_ids) - len(failed)
    print(f"sent report for {call_id} to {delivered}/{len(chat_ids)} chat(s)")
    return delivered > 0


def recent_ended_calls(limit: int = 20, since_hours: float = 24.0) -> list[str]:
    import psycopg

    dsn = os.environ.get("IMVERA_PG_URL", "")
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT call_id FROM call_results "
                "WHERE call_ended = TRUE "
                "AND updated_at > now() - (%s || ' hours')::interval "
                "ORDER BY updated_at DESC LIMIT %s",
                (str(since_hours), limit),
            )
            return [r[0] for r in cur.fetchall()]


def watch(interval_s: float, dry_run: bool, since_hours: float) -> None:
    sent = _load_sent()
    print(f"watching (interval {interval_s}s), already sent: {len(sent)}")
    while True:
        try:
            for call_id in recent_ended_calls(since_hours=since_hours):
                if call_id in sent:
                    continue
                if report_call(call_id, dry_run=dry_run):
                    sent.add(call_id)
                    _save_sent(sent)
        except Exception as exc:
            print(f"watch error: {exc}")
        time.sleep(interval_s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--call-id", default=None)
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--interval", type=float, default=30.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--since-hours", type=float, default=24.0)
    args = ap.parse_args()
    if args.watch:
        watch(args.interval, args.dry_run, args.since_hours)
        return 0
    if not args.call_id:
        print("need --call-id or --watch")
        return 1
    return 0 if report_call(args.call_id, dry_run=args.dry_run) else 1


if __name__ == "__main__":
    raise SystemExit(main())
