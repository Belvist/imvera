#!/usr/bin/env python3
"""Scheduler worker — enqueue + claim + originate (ROADMAP E5)."""
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.pg import maybe_pg_store  # noqa: E402
from core import scheduler as sched  # noqa: E402


def originate_job(pg, job) -> tuple:
    """Returns (ok, detail). Dry-run when MOSS_SCHEDULER_DRY_RUN=1."""
    if os.environ.get("MOSS_SCHEDULER_DRY_RUN", "").strip() in (
            "1", "true", "yes"):
        return True, "dry-run:" + uuid.uuid4().hex[:8]
    if not sched.may_originate(pg, job["elder_id"]):
        return False, "may_originate=false"
    phone = sched.elder_phone(pg, job["elder_id"])
    if not phone:
        return False, "no phone"
    try:
        from adapters.esl import originate_to_number
        result = originate_to_number(phone)
        if result.get("ok"):
            return True, result.get("uuid") or "ok"
        return False, result.get("error") or "esl failed"
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__


def _mark_no_contact(pg, job):
    """Persist family NO_CONTACT when dialer exhausts attempts."""
    call_id = "nc-" + uuid.uuid4().hex[:12]
    try:
        if hasattr(pg, "insert_no_contact_result"):
            pg.insert_no_contact_result(
                call_id, job["elder_id"],
                notes=["недозвон: исчерпаны попытки"],
                summary=("Дозвониться не удалось. "
                         "Близким стоит связаться самостоятельно."))
        pg.enqueue(
            "call.result",
            {"call_id": call_id,
             "verdict": "no_contact",
             "family_status": "no_contact",
             "elder_id": job.get("elder_id"),
             "notes": ["недозвон"]},
            dedup_key=f"call:{call_id}")
    except Exception as e:  # noqa: BLE001
        print(f"[scheduler] no_contact persist failed: {e}", flush=True)


def run_once(pg, worker_id):
    created = sched.enqueue_due_jobs(pg)
    claimed = sched.claim_jobs(pg, worker_id, limit=10)
    for job in claimed:
        jid = job.get("id") or job.get("job_id")
        # Mark in_progress before originate so lease owners see progress.
        try:
            pg._exec(
                "UPDATE call_jobs SET status = 'in_progress', "
                "updated_at = now() WHERE id = %s AND status = 'claimed'",
                (jid,))
        except Exception:  # noqa: BLE001
            pass
        ok, detail = originate_job(pg, job)
        if ok:
            sched.complete_job(pg, jid, "done", result_call_id=str(detail))
        else:
            schedule = sched.load_schedule(pg, job.get("schedule_id")) or {}
            nxt = sched.policy_next_attempt(job, schedule)
            if nxt is None:
                sched.complete_job(
                    pg, jid, "no_contact", error=str(detail)[:200])
                _mark_no_contact(pg, job)
            else:
                sched.requeue_job(pg, job, nxt)
    return created, len(claimed)


def main():
    pg = maybe_pg_store()
    if not getattr(pg, "available", False):
        print("[scheduler] postgres unavailable", flush=True)
        sys.exit(1)
    worker_id = os.environ.get("MOSS_WORKER_ID", "scheduler-1")
    interval = int(os.environ.get("MOSS_SCHEDULER_INTERVAL_SECONDS", "30"))
    print(f"[scheduler] started worker={worker_id} interval={interval}s",
          flush=True)
    while True:
        try:
            created, claimed = run_once(pg, worker_id)
            if created or claimed:
                print(f"[scheduler] enqueued={created} claimed={claimed}",
                      flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[scheduler] error: {e}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
