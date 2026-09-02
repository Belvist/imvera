"""Outbound scheduler / dialer queue (ROADMAP E5).

Postgres-backed job queue with the same lease pattern as the outbox
(``FOR UPDATE SKIP LOCKED``). Schema lives in migration
``006_product_core.sql`` (schedules + call_jobs). Pure policy helpers
(quiet hours, attempt window, kill-switch) need no database.

Lifecycle
---------
1. ``enqueue_due_jobs`` — for each enabled, unpaused schedule whose local
   window is active (or starts today), insert one ``call_jobs`` row.
   Idempotent: skip if a live/done job already exists for that elder in
   the same window.
2. ``claim_jobs`` — lease pending due rows (``lease_owner`` / ``lease_until``).
3. Dialer hook originates the call (or dry-runs).
4. ``complete_job`` — terminal status; or worker requeues via
   ``policy_next_attempt`` when busy / no-answer.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo

from core.consent import has_active_consent

# Terminal statuses allowed by call_jobs CHECK + cancelled for blocked.
_TERMINAL = frozenset({"done", "failed", "no_contact", "cancelled"})

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_ATTEMPT_INTERVAL_MIN = 15


def kill_switch_enabled() -> bool:
    """Global outbound kill-switch (``MOSS_OUTBOUND_KILL_SWITCH=1``)."""
    return os.environ.get("MOSS_OUTBOUND_KILL_SWITCH", "").strip() in (
        "1", "true", "TRUE", "yes", "YES", "on", "ON")


def _as_time(value) -> Optional[time]:
    if value is None:
        return None
    if isinstance(value, time):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, datetime):
        return value.timetz().replace(tzinfo=None) if value.tzinfo else value.time()
    text = str(value).strip()
    if not text:
        return None
    parts = text.split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        s = int(float(parts[2])) if len(parts) > 2 else 0
        return time(h, m, s)
    except (TypeError, ValueError, IndexError):
        return None


def _as_dt(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return None


def _tz(schedule: Mapping[str, Any]) -> ZoneInfo:
    name = (schedule.get("timezone") or "Europe/Moscow").strip() or "Europe/Moscow"
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        return ZoneInfo("Europe/Moscow")


def _now_utc(now=None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    dt = _as_dt(now) or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _quiet_bounds(schedule: Mapping[str, Any]):
    """Support product columns quiet_start/quiet_end and legacy *_local."""
    q_start = _as_time(
        schedule.get("quiet_start") or schedule.get("quiet_start_local"))
    q_end = _as_time(
        schedule.get("quiet_end") or schedule.get("quiet_end_local"))
    return q_start, q_end


def _window_times(schedule: Mapping[str, Any]):
    w_start = _as_time(
        schedule.get("window_start") or schedule.get("window_start_local")
    ) or time(10, 0)
    w_end = _as_time(
        schedule.get("window_end") or schedule.get("window_end_local")
    ) or time(12, 0)
    return w_start, w_end


def _attempt_policy(schedule: Mapping[str, Any]):
    """Read max_attempts / interval from JSONB attempt_policy or flat keys."""
    policy = schedule.get("attempt_policy") or {}
    if isinstance(policy, str):
        try:
            import json
            policy = json.loads(policy)
        except Exception:  # noqa: BLE001
            policy = {}
    if not isinstance(policy, Mapping):
        policy = {}
    max_attempts = int(
        policy.get("max_attempts")
        or schedule.get("max_attempts")
        or DEFAULT_MAX_ATTEMPTS)
    interval = int(
        policy.get("interval_minutes")
        or schedule.get("attempt_interval_minutes")
        or DEFAULT_ATTEMPT_INTERVAL_MIN)
    return max(1, max_attempts), max(1, interval)


def in_quiet_hours(schedule: Mapping[str, Any], now=None) -> bool:
    """True when local clock of ``now`` falls inside quiet hours.

    Overnight windows (e.g. 21:00–08:00) are supported. Missing quiet
    bounds → never quiet.
    """
    q_start, q_end = _quiet_bounds(schedule)
    if q_start is None or q_end is None:
        return False
    local = _now_utc(now).astimezone(_tz(schedule)).time().replace(tzinfo=None)
    if q_start == q_end:
        return False
    if q_start < q_end:
        return q_start <= local < q_end
    return local >= q_start or local < q_end


def policy_next_attempt(job: Mapping[str, Any], schedule: Mapping[str, Any],
                        now=None) -> Optional[datetime]:
    """Next due_at after a failed attempt, or None → NO_CONTACT.

    Default policy: 3 attempts × 15 minutes inside the day's call window.
    Exhausted or past window → None.
    """
    max_attempts, interval_min = _attempt_policy(schedule)
    attempt_no = int(job.get("attempt_no") or 1)
    if attempt_no >= max_attempts:
        return None
    base = _now_utc(now)
    nxt = base + timedelta(minutes=interval_min)
    window_end = _as_dt(job.get("window_end"))
    if window_end is None and schedule:
        # Derive today's window end from the schedule.
        local = base.astimezone(_tz(schedule))
        _, end = _window_bounds(schedule, local.date())
        window_end = end
    if window_end is not None and nxt > window_end:
        return None
    return nxt


def _days_ok(schedule: Mapping[str, Any], local_day: date) -> bool:
    days = schedule.get("days_of_week") or []
    if not days:
        return True
    # Product schema uses ISO 1=Mon..7=Sun; also accept 0=Mon..6=Sun.
    iso = local_day.isoweekday()  # 1..7
    py = local_day.weekday()      # 0..6
    wanted = {int(d) for d in days}
    return iso in wanted or py in wanted


def _window_bounds(schedule: Mapping[str, Any], local_day: date):
    """Return (window_start_utc, window_end_utc) for ``local_day``."""
    tz = _tz(schedule)
    w_start, w_end = _window_times(schedule)
    start_local = datetime.combine(local_day, w_start, tzinfo=tz)
    end_local = datetime.combine(local_day, w_end, tzinfo=tz)
    if end_local <= start_local:
        end_local = end_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _active_window(schedule: Mapping[str, Any], now: datetime):
    """Window that contains ``now``, or today's upcoming window, or None."""
    tz = _tz(schedule)
    local_now = now.astimezone(tz)
    candidates = [local_now.date(), local_now.date() - timedelta(days=1)]
    for day in candidates:
        if not _days_ok(schedule, day):
            continue
        start, end = _window_bounds(schedule, day)
        if start <= now < end:
            return start, end
    day = local_now.date()
    if _days_ok(schedule, day):
        start, end = _window_bounds(schedule, day)
        if now < start:
            return start, end
    return None


def may_originate(pg, elder_id, now=None, schedule=None) -> bool:
    """Consent + kill-switch + quiet hours gate for outbound originate."""
    if kill_switch_enabled():
        return False
    if not has_active_consent(pg, elder_id):
        return False
    if schedule is not None:
        return not in_quiet_hours(schedule, now=now)
    rows = []
    try:
        rows = pg._exec(
            "SELECT * FROM schedules WHERE elder_id = %s AND enabled "
            "AND NOT paused",
            (elder_id,), fetch="all") or []
    except Exception:  # noqa: BLE001
        return False
    for row in rows:
        if in_quiet_hours(row, now=now):
            return False
    return True


def enqueue_due_jobs(pg, now=None) -> int:
    """Create pending jobs for enabled schedules' current/next windows.

    Idempotent per elder+window: skips when a pending/claimed/in_progress/done
    job already sits inside the same window.
    """
    if not getattr(pg, "available", False):
        return 0
    now_utc = _now_utc(now)
    schedules = pg._exec(
        "SELECT * FROM schedules WHERE enabled AND NOT paused",
        fetch="all") or []
    created = 0
    for sched_row in schedules:
        bounds = _active_window(sched_row, now_utc)
        if bounds is None:
            continue
        window_start, window_end = bounds
        if in_quiet_hours(sched_row, now=now_utc):
            continue
        if not has_active_consent(pg, sched_row["elder_id"]):
            continue
        if kill_switch_enabled():
            continue
        due_at = window_start if now_utc < window_start else now_utc
        job_id = "job-" + uuid.uuid4().hex[:16]
        schedule_id = sched_row.get("id") or sched_row.get("schedule_id")
        exists = pg._exec(
            "SELECT 1 FROM call_jobs WHERE elder_id = %s "
            "AND due_at >= %s AND due_at < %s "
            "AND status IN ('pending','claimed','in_progress','done') "
            "LIMIT 1",
            (sched_row["elder_id"], window_start, window_end), fetch="val")
        if exists:
            continue
        inserted = pg._exec(
            "INSERT INTO call_jobs "
            "(id, schedule_id, elder_id, due_at, attempt_no, status) "
            "VALUES (%s, %s, %s, %s, 1, 'pending') "
            "RETURNING id",
            (job_id, schedule_id, sched_row["elder_id"], due_at),
            fetch="val")
        if inserted:
            created += 1
    return created


def claim_jobs(pg, worker_id, limit=10, lock_seconds=60):
    """Lease pending due jobs (``FOR UPDATE SKIP LOCKED``), matching outbox."""
    if not getattr(pg, "available", False):
        return []
    worker_id = (worker_id or "scheduler").strip() or "scheduler"
    rows = pg._exec(
        "UPDATE call_jobs SET status = 'claimed', lease_owner = %s, "
        "lease_until = now() + %s::interval, updated_at = now() "
        "WHERE id = ANY ("
        "  SELECT id FROM call_jobs "
        "  WHERE status = 'pending' AND due_at <= now() "
        "    AND (lease_until IS NULL OR lease_until < now()) "
        "  ORDER BY due_at LIMIT %s "
        "  FOR UPDATE SKIP LOCKED"
        ") RETURNING *",
        (worker_id, f"{int(lock_seconds)} seconds", int(limit)),
        fetch="all")
    return rows or []


def complete_job(pg, job_id, status, result_call_id=None, error=None) -> bool:
    """Mark a job terminal. Returns True when a row updated."""
    if status not in _TERMINAL:
        raise ValueError(f"invalid terminal status: {status}")
    if not getattr(pg, "available", False):
        return False
    n = pg._exec(
        "UPDATE call_jobs SET status = %s, result_call_id = %s, "
        "last_error = %s, lease_owner = NULL, lease_until = NULL, "
        "updated_at = now() "
        "WHERE id = %s "
        "AND status IN ('pending', 'claimed', 'in_progress')",
        (status, result_call_id, error, job_id))
    return bool(n)


def requeue_job(pg, job, next_due: datetime) -> bool:
    """Bump attempt_no and return the job to pending at ``next_due``."""
    if not getattr(pg, "available", False):
        return False
    jid = job.get("id") or job.get("job_id")
    n = pg._exec(
        "UPDATE call_jobs SET status = 'pending', due_at = %s, "
        "attempt_no = attempt_no + 1, lease_owner = NULL, lease_until = NULL, "
        "last_error = NULL, updated_at = now() "
        "WHERE id = %s AND status IN ('claimed', 'in_progress')",
        (next_due, jid))
    return bool(n)


def load_schedule(pg, schedule_id):
    if not getattr(pg, "available", False) or not schedule_id:
        return None
    return pg._exec(
        "SELECT * FROM schedules WHERE id = %s",
        (schedule_id,), fetch="one")


def elder_phone(pg, elder_id) -> Optional[str]:
    if not getattr(pg, "available", False):
        return None
    row = pg._exec(
        "SELECT phone FROM elders WHERE person_id = %s",
        (elder_id,), fetch="one")
    if not row:
        return None
    return row.get("phone")
