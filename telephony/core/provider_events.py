"""Durable provider-event workflow (Phase 2).

Inbox contract (drill: a webhook replayed 100x → one processing):
1. ``ingest_provider_event`` commits the event first (durable) with
   ``ON CONFLICT DO NOTHING`` — only the first sighting proceeds.
2. Side effects (attempt transition + outbox enqueue + processed_at) run in a
   SINGLE transaction. Attempt transitions are guarded UPDATEs, so a late
   ``answered`` cannot corrupt a ``completed`` attempt, and a ``timeout``
   cannot double-fire.
3. ``provider_events.processed_at`` is set in the same transaction as the
   side effects — no split-brain between "event processed" and "state
   applied". A crash before commit leaves the event unprocessed for the
   reconciliation sweep (``unprocessed_events``).

The webhook path never CREATES attempts or calls: retries are the scheduler's
job (explicit attempt_no). The inbox only records what the provider observed.
"""

import json


# kind -> (attempt transition, is_terminal)
_RING = {"call_started", "ringing", "call_attempt_started"}
_ANSWERED = {"answered", "answer"}
_COMPLETED = {"completed", "hangup", "call_ended"}
_FAILED = {"failed", "no_answer", "timeout", "busy", "canceled"}


def _attempt_id_for(event, pg):
    """Resolve the attempt row: explicit attempt_id > provider callout_id."""
    aid = event.get("attempt_id")
    if aid:
        return aid
    callout = event.get("callout_id") or (
        event.get("payload") or {}).get("callout_id")
    if callout:
        row = pg.get_attempt_by_callout(callout)
        if row:
            return row["attempt_id"]
    return None


def _apply_provider_event(pg, event_id, kind, payload, call_id, attempt_id):
    """Apply side effects + mark processed, in ONE transaction."""
    conn = pg._conn()
    try:
        aid = _attempt_id_for(
            {"attempt_id": attempt_id, "call_id": call_id, "payload": payload},
            pg)
        transitioned = None
        new_status = None
        if aid is not None:
            if kind in _RING:
                transitioned = pg.mark_ringing(aid, callout_id=call_id,
                                               conn=conn)
                new_status = "ringing"
            elif kind in _ANSWERED:
                transitioned = pg.mark_answered(aid, conn=conn)
                new_status = "answered"
            elif kind in _COMPLETED:
                dur = (payload.get("duration_seconds") or
                       payload.get("duration"))
                transitioned = pg.mark_completed(
                    aid, duration_seconds=dur,
                    provider_event_id=event_id, conn=conn)
                new_status = "completed"
            elif kind in _FAILED:
                transitioned = pg.mark_failed(
                    aid, cause=kind, provider_event_id=event_id, conn=conn)
                new_status = "failed"

        # Outbox side effect: notify downstream on terminal state. Written in
        # the SAME tx; dedup_key makes reprocessing a no-op. The consumer of
        # ``call.result`` reads ``verdict``/``notes`` — keep the same contract
        # as end_call (orchestrator). The webhook path has no dialogue with
        # Vera, so there is no safety assessment: the mapping is honest
        # ("unknown" / "no_answer"), never a fabricated GREEN or RED.
        if new_status in ("completed", "failed") and aid:
            attempt = pg.get_attempt(aid)
            if attempt:
                pg.enqueue(
                    "call.result",
                    {"call_id": attempt["call_id"], "attempt_id": aid,
                     "status": new_status,
                     "verdict": "unknown" if new_status == "completed"
                     else "no_answer",
                     "notes": [],
                     "event_id": event_id},
                    dedup_key=f"provider:{event_id}", conn=conn)
            if attempt and attempt["call_id"]:
                pg.close_attempt(attempt["call_id"], conn=conn)

        pg.mark_event_processed(event_id, conn=conn)
        conn.commit()
        return {"processed": True, "event_id": event_id, "kind": kind,
                "attempt_id": aid, "transition_applied": transitioned,
                "new_status": new_status}
    except Exception:  # noqa: BLE001
        conn.rollback()
        raise
    finally:
        pg.release(conn)


def process_provider_event(pg, event):
    """Ingest + apply one provider event. Returns a result dict.

    ``event``: dict with event_id, kind, and optional call_id/attempt_id/
    callout_id/payload. Pure idempotency: repeated events return
    ``{"processed": False, "reason": "duplicate"}``.
    """
    event_id = event["event_id"]
    kind = event["kind"]
    payload = event.get("payload") or {}
    call_id = event.get("call_id")
    attempt_id = event.get("attempt_id")
    provider = event.get("provider", "exolve")

    inserted = pg.ingest_provider_event(
        event_id, kind, payload,
        provider=provider, call_id=call_id, attempt_id=attempt_id)
    if not inserted:
        row = pg.event(event_id)
        return {"processed": False, "reason": "duplicate",
                "event_id": event_id, "status": (row or {}).get("kind")}

    return _apply_provider_event(pg, event_id, kind, payload, call_id,
                                 attempt_id)


def reconcile_unprocessed(pg, limit=100):
    """Re-drive events that were ingested but never processed (crash window).
    Returns the number reprocessed."""
    n = 0
    for ev in pg.unprocessed_events(limit=limit):
        _apply_provider_event(
            pg, ev["event_id"], ev["kind"], ev["payload"], ev["call_id"],
            ev["attempt_id"])
        n += 1
    return n