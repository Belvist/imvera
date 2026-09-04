"""Unit tests for ROADMAP E5 scheduler (pure policy + mocked PG).

Always-on: quiet hours, attempt policy → NO_CONTACT, kill switch,
idempotent enqueue, exclusive lease claim (mock). Integration against
live Postgres is skipped unless MOSS_PG_URL is set.
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, time, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import scheduler as sched  # noqa: E402
from core.consent import has_active_consent  # noqa: E402


def _utc(y, m, d, hh, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc)


class QuietHoursTests(unittest.TestCase):
    def test_daytime_quiet_window(self):
        schedule = {
            "timezone": "UTC",
            "quiet_start": time(13, 0),
            "quiet_end": time(15, 0),
        }
        self.assertTrue(sched.in_quiet_hours(schedule, _utc(2026, 9, 2, 13, 30)))
        self.assertFalse(sched.in_quiet_hours(schedule, _utc(2026, 9, 2, 12, 59)))
        self.assertFalse(sched.in_quiet_hours(schedule, _utc(2026, 9, 2, 15, 0)))

    def test_overnight_quiet_window(self):
        schedule = {
            "timezone": "UTC",
            "quiet_start": "21:00",
            "quiet_end": "08:00",
        }
        self.assertTrue(sched.in_quiet_hours(schedule, _utc(2026, 9, 2, 22, 0)))
        self.assertTrue(sched.in_quiet_hours(schedule, _utc(2026, 9, 2, 3, 0)))
        self.assertFalse(sched.in_quiet_hours(schedule, _utc(2026, 9, 2, 12, 0)))

    def test_missing_bounds_never_quiet(self):
        self.assertFalse(sched.in_quiet_hours({"timezone": "UTC"}, _utc(2026, 9, 2, 3)))


class AttemptPolicyTests(unittest.TestCase):
    def test_next_attempt_inside_window(self):
        job = {"attempt_no": 1, "window_end": _utc(2026, 9, 2, 14, 0)}
        schedule = {"attempt_policy": {"max_attempts": 3, "interval_minutes": 15}}
        now = _utc(2026, 9, 2, 10, 0)
        nxt = sched.policy_next_attempt(job, schedule, now=now)
        self.assertEqual(nxt, now + timedelta(minutes=15))

    def test_exhausted_attempts_returns_none(self):
        job = {"attempt_no": 3, "window_end": _utc(2026, 9, 2, 18, 0)}
        schedule = {"attempt_policy": {"max_attempts": 3, "interval_minutes": 15}}
        self.assertIsNone(
            sched.policy_next_attempt(job, schedule, now=_utc(2026, 9, 2, 10)))

    def test_past_window_returns_none_no_contact(self):
        job = {"attempt_no": 1, "window_end": _utc(2026, 9, 2, 10, 5)}
        schedule = {"attempt_policy": {"max_attempts": 3, "interval_minutes": 15}}
        self.assertIsNone(
            sched.policy_next_attempt(job, schedule, now=_utc(2026, 9, 2, 10, 0)))

    def test_three_failures_then_no_contact(self):
        """Simulate the product policy: 3 × 15 min → NO_CONTACT."""
        schedule = {"attempt_policy": {"max_attempts": 3, "interval_minutes": 15}}
        window_end = _utc(2026, 9, 2, 18, 0)
        now = _utc(2026, 9, 2, 10, 0)
        job = {"attempt_no": 1, "window_end": window_end}
        for expected_attempt in (1, 2):
            nxt = sched.policy_next_attempt(job, schedule, now=now)
            self.assertIsNotNone(nxt, f"attempt {expected_attempt} should retry")
            job = {"attempt_no": expected_attempt + 1, "window_end": window_end}
            now = nxt
        self.assertIsNone(sched.policy_next_attempt(job, schedule, now=now))


class KillSwitchTests(unittest.TestCase):
    def test_kill_switch_env(self):
        with mock.patch.dict(os.environ, {"MOSS_OUTBOUND_KILL_SWITCH": "1"}):
            self.assertTrue(sched.kill_switch_enabled())
        with mock.patch.dict(os.environ, {"MOSS_OUTBOUND_KILL_SWITCH": ""}):
            self.assertFalse(sched.kill_switch_enabled())


class _FakePg:
    """Minimal in-memory stand-in for enqueue / claim exclusivity tests."""

    available = True

    def __init__(self):
        self.schedules = []
        self.jobs = {}  # id -> row
        self.consents = set()
        self._claim_lock = set()

    def has_active_consent(self, person_id):
        return person_id in self.consents

    def _exec(self, sql, params=(), fetch=None):
        sql_n = " ".join(sql.split())
        if "FROM schedules WHERE enabled AND NOT paused" in sql_n:
            rows = [s for s in self.schedules
                    if s.get("enabled") and not s.get("paused")]
            return rows if fetch in (None, "all") else rows
        if "FROM schedules WHERE elder_id" in sql_n:
            eid = params[0]
            rows = [s for s in self.schedules
                    if s.get("elder_id") == eid and s.get("enabled")
                    and not s.get("paused")]
            return rows if fetch == "all" else rows
        if "FROM schedules WHERE id" in sql_n:
            sid = params[0]
            for s in self.schedules:
                if s.get("id") == sid:
                    return s
            return None
        if "SELECT 1 FROM call_jobs WHERE elder_id" in sql_n:
            elder_id, window_start, window_end = params
            for job in self.jobs.values():
                if (job["elder_id"] == elder_id
                        and window_start <= job["due_at"] < window_end
                        and job["status"] in (
                            "pending", "claimed", "in_progress", "done")):
                    return 1 if fetch == "val" else {"x": 1}
            return None
        if sql_n.startswith("INSERT INTO call_jobs"):
            job_id, schedule_id, elder_id, due_at = params[:4]
            row = {
                "id": job_id,
                "schedule_id": schedule_id,
                "elder_id": elder_id,
                "due_at": due_at,
                "attempt_no": 1,
                "status": "pending",
                "lease_owner": None,
                "lease_until": None,
            }
            self.jobs[job_id] = row
            return job_id if fetch == "val" else 1
        if "UPDATE call_jobs SET status = 'claimed'" in sql_n:
            worker_id, _lease_iv, limit = params
            claimed = []
            now = datetime.now(timezone.utc)
            for job in sorted(self.jobs.values(), key=lambda r: r["due_at"]):
                if len(claimed) >= int(limit):
                    break
                if job["status"] != "pending":
                    continue
                if job["due_at"] > now:
                    continue
                if job["id"] in self._claim_lock:
                    continue
                job["status"] = "claimed"
                job["lease_owner"] = worker_id
                job["lease_until"] = now + timedelta(seconds=60)
                claimed.append(dict(job))
            return claimed if fetch == "all" else claimed
        if "UPDATE call_jobs SET status =" in sql_n and "lease_owner = NULL" in sql_n:
            status, result_call_id, error, job_id = params
            job = self.jobs.get(job_id)
            if not job or job["status"] not in (
                    "pending", "claimed", "in_progress"):
                return 0
            job["status"] = status
            job["result_call_id"] = result_call_id
            job["last_error"] = error
            job["lease_owner"] = None
            job["lease_until"] = None
            return 1
        raise AssertionError(f"unexpected SQL in fake pg: {sql_n[:140]}")


class EnqueueIdempotencyTests(unittest.TestCase):
    def test_no_double_enqueue_same_elder_window(self):
        pg = _FakePg()
        now = _utc(2026, 9, 2, 10, 30)  # Wed inside 10–12 UTC
        pg.consents.add("elder-1")
        pg.schedules.append({
            "id": "sch-1",
            "elder_id": "elder-1",
            "enabled": True,
            "paused": False,
            "days_of_week": [1, 2, 3, 4, 5, 6, 7],
            "window_start": time(10, 0),
            "window_end": time(12, 0),
            "timezone": "UTC",
            "quiet_start": None,
            "quiet_end": None,
            "attempt_policy": {"max_attempts": 3, "interval_minutes": 15},
        })
        with mock.patch.dict(os.environ, {"MOSS_OUTBOUND_KILL_SWITCH": ""}):
            n1 = sched.enqueue_due_jobs(pg, now=now)
            n2 = sched.enqueue_due_jobs(pg, now=now)
        self.assertEqual(n1, 1)
        self.assertEqual(n2, 0)
        self.assertEqual(len(pg.jobs), 1)


class LeaseClaimTests(unittest.TestCase):
    def test_claim_exclusive_skip_locked(self):
        pg = _FakePg()
        now = datetime.now(timezone.utc) - timedelta(seconds=1)
        pg.jobs["j1"] = {
            "id": "j1",
            "schedule_id": "sch-1",
            "elder_id": "elder-1",
            "due_at": now,
            "attempt_no": 1,
            "status": "pending",
            "lease_owner": None,
            "lease_until": None,
        }
        pg._claim_lock.add("j1")
        got_b = sched.claim_jobs(pg, worker_id="worker-b", limit=10)
        self.assertEqual(got_b, [])
        pg._claim_lock.clear()
        got_a = sched.claim_jobs(pg, worker_id="worker-a", limit=10)
        self.assertEqual(len(got_a), 1)
        self.assertEqual(got_a[0]["lease_owner"], "worker-a")
        self.assertEqual(got_a[0]["status"], "claimed")
        got_again = sched.claim_jobs(pg, worker_id="worker-b", limit=10)
        self.assertEqual(got_again, [])


class MayOriginateTests(unittest.TestCase):
    def test_kill_switch_blocks(self):
        pg = _FakePg()
        pg.consents.add("elder-1")
        with mock.patch.dict(os.environ, {"MOSS_OUTBOUND_KILL_SWITCH": "1"}):
            self.assertFalse(sched.may_originate(pg, "elder-1"))

    def test_no_consent_blocks(self):
        pg = _FakePg()
        with mock.patch.dict(os.environ, {"MOSS_OUTBOUND_KILL_SWITCH": ""}):
            self.assertFalse(sched.may_originate(pg, "elder-1"))

    def test_quiet_hours_blocks_with_schedule(self):
        pg = _FakePg()
        pg.consents.add("elder-1")
        schedule = {
            "timezone": "UTC",
            "quiet_start": time(0, 0),
            "quiet_end": time(23, 59),
        }
        with mock.patch.dict(os.environ, {"MOSS_OUTBOUND_KILL_SWITCH": ""}):
            self.assertFalse(
                sched.may_originate(
                    pg, "elder-1", now=_utc(2026, 9, 2, 12), schedule=schedule))

    def test_consent_ok_allows(self):
        pg = _FakePg()
        pg.consents.add("elder-1")
        with mock.patch.dict(os.environ, {"MOSS_OUTBOUND_KILL_SWITCH": ""}):
            self.assertTrue(sched.may_originate(pg, "elder-1"))
            self.assertTrue(has_active_consent(pg, "elder-1"))


class OriginateJobEslTests(unittest.TestCase):
    def test_esl_failure_records_freeswitch_message(self):
        from workers.scheduler_worker_main import originate_job

        job = {"elder_id": "elder-1"}
        with mock.patch.dict(os.environ, {
                "MOSS_SCHEDULER_DRY_RUN": "",
                "MOSS_OUTBOUND_KILL_SWITCH": ""}), \
                mock.patch("core.scheduler.may_originate", return_value=True), \
                mock.patch("core.scheduler.elder_phone",
                           return_value="+79001234567"), \
                mock.patch("adapters.esl.originate_to_number",
                           return_value={"ok": False, "uuid": None,
                                         "message": "NO_ROUTE_DESTINATION"}):
            ok, detail = originate_job(mock.Mock(), job)
        self.assertFalse(ok)
        self.assertEqual(detail, "NO_ROUTE_DESTINATION")


@unittest.skipUnless(os.environ.get("MOSS_PG_URL"), "MOSS_PG_URL not set")
class LivePgSchedulerTests(unittest.TestCase):
    def test_claim_sql_parses(self):
        from adapters.pg import maybe_pg_store
        pg = maybe_pg_store()
        if not getattr(pg, "available", False):
            self.skipTest("postgres unavailable")
        rows = sched.claim_jobs(pg, worker_id="test-scheduler", limit=1)
        self.assertIsInstance(rows, list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
