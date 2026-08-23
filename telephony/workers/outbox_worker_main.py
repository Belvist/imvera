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
                incidents.maybe_open(
                    payload.get("call_id"),
                    payload.get("verdict"),
                    notes=payload.get("notes") or [])
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