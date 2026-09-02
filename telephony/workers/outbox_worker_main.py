#!/usr/bin/env python3
"""Standalone business worker: outbox delivery + incident escalation.

Extracted from the telephony process (architecture directive 2026-08-21):
realtime call handling must not share a process with background business
processing — an outbox backlog or escalation tick must never steal CPU from
live audio. Run as its own deployment (compose service `workflow`):

    python workers/outbox_worker_main.py

Requires Postgres (MOSS_PG_URL). Idempotent: lease-based claiming via
FOR UPDATE SKIP LOCKED, so several replicas can run safely.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _paths import ensure_runtime_scripts  # noqa: E402

ensure_runtime_scripts()

from adapters.pg import maybe_pg_store  # noqa: E402
from core.delivery import DeliveryRouter  # noqa: E402
from core.incidents import IncidentEngine  # noqa: E402
from core.outbox_worker import OutboxWorker  # noqa: E402


def _dispatch(incidents):
    """Same topic routing as Serve._dispatch_outbox (call.result opens
    incidents; incident.notify delivers one action; others are acked)."""
    def _route(topic, payload, msg_id):
        try:
            if topic == "call.result":
                call_id = payload.get("call_id")
                verdict = payload.get("verdict")
                family_status = (payload.get("family_status") or "").lower()
                # Prefer family_status when present (E2).
                open_verdict = (
                    "alert" if family_status == "red" else verdict)
                household_id = payload.get("household_id")
                elder_id = payload.get("elder_id")
                if (not household_id) and call_id and hasattr(
                        incidents.pg, "household_for_call"):
                    try:
                        household_id, elder_id = (
                            incidents.pg.household_for_call(call_id))
                    except Exception:  # noqa: BLE001
                        pass
                incidents.maybe_open(
                    call_id,
                    open_verdict,
                    notes=payload.get("notes") or [],
                    household_id=household_id,
                    elder_id=elder_id)
                # Non-RED family status: still emit a lightweight status
                # notify when MOSS_NOTIFY_ALL_STATUSES=1 (E6).
                if (os.environ.get("MOSS_NOTIFY_ALL_STATUSES", "").strip()
                        in ("1", "true", "yes")
                        and family_status
                        and family_status != "red"):
                    _notify_status(incidents, payload, household_id)
                return True
            if topic == "incident.notify":
                return bool(incidents.deliver(payload))
            print(f"[outbox] {msg_id} topic={topic} (no consumer, acked)",
                  flush=True)
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[outbox] dispatch error: {e}", flush=True)
            return False
    return _route


def _notify_status(incidents, payload, household_id):
    """Best-effort status push/telegram after every call (optional)."""
    summary = payload.get("summary_for_family") or ""
    status = payload.get("family_status") or ""
    text = f"IMVERA: статус {status.upper()}. {summary}".strip()
    contacts = incidents._load_contacts(household_id=household_id)
    for ch in ("push", "telegram"):
        addr = contacts.get(ch)
        if not addr:
            continue
        try:
            incidents.router.send(ch, addr, text)
        except Exception:  # noqa: BLE001
            pass


def main():
    pg = maybe_pg_store()
    if not getattr(pg, "available", False):
        print("[workflow] postgres unavailable", flush=True)
        sys.exit(1)
    incidents = IncidentEngine(pg, DeliveryRouter())
    worker = OutboxWorker(
        pg, _dispatch(incidents),
        worker_id=os.environ.get("MOSS_WORKER_ID", "workflow"),
        tick=incidents.tick,
    )
    print("[workflow] outbox worker started", flush=True)
    worker.start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        worker.stop()


if __name__ == "__main__":
    main()