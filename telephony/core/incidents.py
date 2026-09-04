"""Phase 3: Incident Engine (I1-I7).

The durable escalation machine. An incident is opened when a call's final
verdict is RED (``alert``); its ``incident_actions`` rows are the ordered
escalation plan (telegram -> sms -> call). Delivery is driven through the
transactional outbox (proven in Phase 2): each action is delivered by an
``incident.notify`` message deduped on ``incident:<id>:<action_id>``, so a
restart, a replayed webhook or a double enqueue never double-notifies.

Lifecycle (guarded transitions, actor+reason audited):
    open -> ack -> checking -> resolved | false_alarm

Timers are deadlines computed from Postgres ``now()`` (single source of
truth): an ``open`` incident past the ACK deadline with no confirmed action
is escalated (next channel, ``escalation_level`` bump); an ``ack``/``checking``
incident past the RESOLVE deadline is flagged for the human operator.
``tick()`` runs on every outbox-worker poll.
"""

import os
import time
import uuid

INCIDENT_VERDICTS = {"alert"}  # SafetyEngine RED -> incident

ACK_SECONDS = int(os.environ.get("MOSS_INCIDENT_ACK_SECONDS", "180"))
RESOLVE_SECONDS = int(os.environ.get("MOSS_INCIDENT_RESOLVE_SECONDS", "900"))


class IncidentEngine:
    def __init__(self, pg, router, ack_seconds=ACK_SECONDS,
                 resolve_seconds=RESOLVE_SECONDS):
        self.pg = pg
        self.router = router
        self.ack_seconds = ack_seconds
        self.resolve_seconds = resolve_seconds
        self.channels = router.channel_names()

    # ------------------------------------------------------------------ #
    # Opening: RED verdict -> incident + escalation plan.

    def maybe_open(self, call_id, verdict, notes=None, contacts=None,
                   household_id=None, elder_id=None):
        """Create an incident from a RED verdict (idempotent). Returns the
        incident id, or None when the verdict is not RED."""
        # Accept family_status "red" as well as legacy agent "alert".
        v = (verdict or "").strip().lower()
        if v in ("red", "alert"):
            v = "alert"
        if v not in INCIDENT_VERDICTS:
            return None
        # Idempotency by CALL, not by random id: outbox delivery is
        # at-least-once, so a replayed call.result (crash between dispatch
        # and resolve_outbox, lease expiry) must never open a second
        # incident for the same call. ON CONFLICT (id) cannot help — the
        # uuid is fresh on every attempt.
        existing = self.pg.get_incident_by_call(call_id)
        if existing is not None:
            return existing["id"]
        incident_id = "inc-" + uuid.uuid4().hex[:12]
        self.pg.open_incident(incident_id, call_id, v,
                              notes=notes or [])
        if household_id and hasattr(self.pg, "set_incident_household"):
            try:
                self.pg.set_incident_household(
                    incident_id, household_id, elder_id=elder_id)
            except Exception:  # noqa: BLE001
                pass
        if contacts is None:
            contacts = self._load_contacts(household_id=household_id,
                                           elder_id=elder_id)
        planned = self._build_plan(incident_id, contacts=contacts)
        self.pg.audit("incident.opened", "safety_engine", "incident",
                      incident_id, {"call_id": call_id, "verdict": v,
                                    "notes": notes or []})
        if planned == 0:
            # Never manufacture a fake "telegram/unset" action: it looks
            # routable but can never notify anyone. Keep the incident open,
            # mark it escalated, and leave an explicit durable audit event for
            # operator alerting/observability.
            self.pg.bump_escalation(incident_id)
            self.pg.audit("incident.notify.unroutable", "delivery",
                          "incident", incident_id,
                          {"reason": "no configured family contact"})
        first = self.pg.next_queued_action(incident_id)
        if first is not None:
            self._enqueue_deliver(incident_id, first["id"])
        return incident_id

    def _load_contacts(self, household_id=None, elder_id=None):
        """Load contacts from PG when available; else empty → ENV fallback."""
        rows = []
        if household_id and hasattr(self.pg, "list_contacts"):
            try:
                rows = self.pg.list_contacts(household_id,
                                             elder_id=elder_id) or []
            except Exception:  # noqa: BLE001
                rows = []
        if hasattr(self.router, "contacts_dict"):
            return self.router.contacts_dict(rows)
        return {}

    def _build_plan(self, incident_id, contacts=None):
        """Ordered escalation plan from configured channels + contacts.

        Contacts: dict channel→address from household DB (E6) or ENV
        defaults (MOSS_FAMILY_CHAT_ID / MOSS_FAMILY_PHONE).
        """
        contacts = contacts or {}
        order = 0
        for ch in self.channels:
            contact = contacts.get(ch) or _default_contact(ch)
            if not contact:
                continue
            self.pg.queue_action(incident_id, ch, contact, order)
            order += 1
        return order

    def _enqueue_deliver(self, incident_id, action_id):
        self.pg.enqueue(
            "incident.notify",
            {"incident_id": incident_id, "action_id": action_id},
            dedup_key=f"incident:{incident_id}:{action_id}")

    # ------------------------------------------------------------------ #
    # Delivery: one action attempt per outbox message.

    def deliver(self, payload):
        """Dispatch handler for topic ``incident.notify``. Returns True when
        the action is terminal (already sent/confirmed or incident closed)."""
        incident_id = payload.get("incident_id")
        action_id = payload.get("action_id")
        incident = self.pg.get_incident(incident_id)
        if incident is None or incident["status"] in ("resolved",
                                                      "false_alarm"):
            return True
        action = self.pg.get_action(action_id)
        if action is None or action["status"] in ("sent", "confirmed"):
            return True
        ok, detail = self.router.send(action["channel"], action["contact"],
                                      _message_for(incident))
        if ok:
            self.pg.mark_action_sent(action_id, detail)
            self.pg.audit("incident.notify.sent", "delivery", "incident",
                          incident_id,
                          {"channel": action["channel"],
                           "action_id": action_id, "detail": detail or ""})
            return True
        self.pg.mark_action_failed(action_id, detail)
        self.pg.audit("incident.notify.failed", "delivery", "incident",
                      incident_id,
                      {"channel": action["channel"], "action_id": action_id,
                       "detail": detail or ""})
        nxt = self.pg.next_queued_action(incident_id)
        if nxt is not None:
            self._enqueue_deliver(incident_id, nxt["id"])
            return True
        # All channels exhausted.
        self.pg.bump_escalation(incident_id)
        return True

    # ------------------------------------------------------------------ #
    # ACK / resolve (family or operator actions).

    def ack(self, incident_id, actor, action_id=None, note=None):
        """Family member confirms they are aware. Marks the confirming action
        confirmed and moves open -> ack -> checking."""
        if action_id:
            act = self.pg.get_action(action_id)
            if act is not None and act["incident_id"] == incident_id and \
                    act["status"] in ("queued", "sent", "failed"):
                self.pg.mark_action_confirmed(action_id, actor, note)
        moved = self.pg.transition_incident(
            incident_id, ("open", "ack", "checking"), "ack", actor,
            note or "family ack")
        self.pg.transition_incident(incident_id, ("open", "ack"), "checking",
                                    actor, note or "family ack")
        return moved

    def resolve(self, incident_id, actor, reason):
        moved = self.pg.transition_incident(
            incident_id, ("ack", "checking", "open"), "resolved", actor,
            reason, assigns=(("resolved_at", "now()"),))
        return moved

    def false_alarm(self, incident_id, actor, reason):
        moved = self.pg.transition_incident(
            incident_id, ("open", "ack", "checking"), "false_alarm", actor,
            reason)
        return moved

    # ------------------------------------------------------------------ #
    # Timers: escalate unacked, flag overdue resolve.

    def tick(self):
        """Called on every outbox-worker poll. Escalates open incidents past
        the ack deadline and flags ack/checking past the resolve deadline."""
        rows = self.pg.escalation_overdue(self.ack_seconds,
                                          self.resolve_seconds) or []
        for inc in rows:
            if inc["status"] == "open":
                self.pg.bump_escalation(inc["id"])
                nxt = self.pg.next_queued_action(inc["id"])
                if nxt is not None:
                    self._enqueue_deliver(inc["id"], nxt["id"])
            else:
                self.pg.audit("incident.overdue.resolve", "system",
                              "incident", inc["id"],
                              {"status": inc["status"]})
        return len(rows)

    # ------------------------------------------------------------------ #
    def close(self):
        pass


def _default_contact(channel):
    if channel == "push":
        return os.environ.get("MOSS_FAMILY_PUSH_TOKEN", "")
    if channel in ("sms", "call"):
        return os.environ.get("MOSS_FAMILY_PHONE", "")
    return ""


def _message_for(incident):
    sev = incident.get("severity") or "red"
    level = incident.get("escalation_level") or 0
    head = "🚨" if level < 1 else "🚨🚨" if level < 2 else "🚨🚨🚨"
    return (f"{head} MossVoice: тревога для звонка {incident.get('call_id')} "
            f"(severity={sev}, escalation={level}). "
            f"Подтвердите, что вы в курсе.")


def _now_ts():
    return time.time()