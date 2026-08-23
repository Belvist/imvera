"""PgStore: durable Postgres adapter for the MossVoice data core.

Authoritative state lives HERE (Phase 2): call_sessions, call_attempts,
dialogue_turns, call_results, provider_events, outbox_messages, incidents,
consents, audit_log. Redis/MinIO are caches/objects around this truth.

Design notes
------------
- Lazy-imports psycopg/psycopg_pool so the offline suite and the image work
  without a database; constructing pings the server and raises PgUnavailable
  when unreachable.
- Idempotency by construction: provider_events PK == provider event id
  (INSERT ... ON CONFLICT DO NOTHING); outbox has a unique dedup_key.
- Attempt transitions are GUARDED updates: ``UPDATE ... WHERE status IN ...``
  returns rowcount 0 when the attempt already left the allowed set, so a late
  ``answered`` can never corrupt a ``completed`` attempt (and a timeout cannot
  double-fire).
"""

import json
import os
from contextlib import contextmanager


class PgUnavailable(Exception):
    """Postgres is not reachable / not configured."""


NOW = object()  # sentinel → renders as SQL now() in an assignment


class _NoPg:
    """Stand-in when Postgres is not configured (offline dev/tests)."""

    available = False
    degraded = False

    def __getattr__(self, name):
        raise PgUnavailable("Postgres not configured (MOSS_PG_URL unset)")

    def close(self):
        pass


_NO_PG = _NoPg()


def _default_url():
    return os.environ.get("MOSS_PG_URL", "")


class PgStore:
    """Thin, SQL-first facade over psycopg3. Every method is idempotent or
    guarded; mutation methods accept an optional ``conn`` so callers can run
    several steps in one transaction."""

    def __init__(self, url=None, pool_min=1, pool_max=5, connect_timeout=8):
        self.url = url or _default_url()
        if not self.url:
            raise PgUnavailable("MOSS_PG_URL is not set")
        from psycopg_pool import ConnectionPool

        self.available = True
        self.degraded = False
        self._pool = ConnectionPool(
            self.url,
            min_size=pool_min,
            max_size=pool_max,
            kwargs={"connect_timeout": connect_timeout},
            open=False,
        )
        self._pool.open()
        self._pool.wait()  # fail fast: pings the server

    def close(self):
        try:
            self._pool.close()
        except Exception:  # noqa: BLE001
            pass

    def __del__(self):
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    # Connection management
    # ------------------------------------------------------------------ #
    @contextmanager
    def conn(self):
        """Check out a pooled connection; returned to the pool on exit."""
        c = self._pool.getconn(timeout=8)
        try:
            yield c
        finally:
            self._pool.putconn(c)

    def _conn(self):
        return self._pool.getconn(timeout=8)

    def release(self, conn):
        try:
            self._pool.putconn(conn)
        except Exception:  # noqa: BLE001
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def _exec(self, sql, params=(), conn=None, fetch=None):
        """Run one statement. fetch: None | 'one' | 'all' | 'val'."""
        from psycopg.rows import dict_row

        own = conn is None
        if own:
            conn = self._conn()
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                if fetch == "one":
                    out = cur.fetchone()
                elif fetch == "all":
                    out = cur.fetchall()
                elif fetch == "val":
                    row = cur.fetchone()
                    out = next(iter(row.values())) if row else None
                else:
                    out = cur.rowcount
                if own:
                    conn.commit()
                return out
        finally:
            if own:
                self.release(conn)

    def ping(self):
        return self._exec("SELECT 1", fetch="val")

    def audit(self, action, actor, entity=None, entity_id=None, detail=None,
              conn=None):
        self._exec(
            "INSERT INTO audit_log (actor, action, entity, entity_id, detail) "
            "VALUES (%s, %s, %s, %s, %s)",
            (actor, action, entity, entity_id,
             json.dumps(detail or {}, ensure_ascii=False)),
            conn=conn)

    # ------------------------------------------------------------------ #
    # Call sessions + dialogue turns (Recorder replacement)
    # ------------------------------------------------------------------ #
    def new_call(self, call_id, caller_id=None, consent_id=None,
                 retention_days=90, conn=None):
        self._exec(
            "INSERT INTO call_sessions (call_id, caller_id, consent_id, "
            "status, retention_days) VALUES (%s, %s, %s, 'active', %s) "
            "ON CONFLICT (call_id) DO NOTHING",
            (call_id, caller_id, consent_id, retention_days), conn=conn)

    def add_turn(self, call_id, role, text, source="stt", confidence=None,
                 audio_key=None, conn=None):
        return self._exec(
            "INSERT INTO dialogue_turns "
            "(call_id, role, text, source, confidence, audio_key) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING turn_id",
            (call_id, role, text, source, confidence, audio_key),
            fetch="val", conn=conn)

    def turns(self, call_id):
        return self._exec(
            "SELECT turn_id, role, text, source, confidence, audio_key, ts "
            "FROM dialogue_turns WHERE call_id = %s ORDER BY turn_id",
            (call_id,), fetch="all")

    def finalize_call(self, call_id, verdict, confidence=None, notes=None,
                      conn=None):
        """Upsert the verdict and mark the session complete atomically."""
        notes = notes or []
        if isinstance(notes, str):
            notes = [notes]
        own = conn is None
        if own:
            conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO call_results (call_id, verdict, confidence, "
                    "notes) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (call_id) DO UPDATE SET "
                    "verdict = EXCLUDED.verdict, "
                    "confidence = EXCLUDED.confidence, "
                    "notes = EXCLUDED.notes",
                    (call_id, verdict, confidence,
                     json.dumps(notes, ensure_ascii=False)))
                cur.execute(
                    "UPDATE call_sessions SET status = 'completed', "
                    "ended_at = now(), result = %s WHERE call_id = %s",
                    (json.dumps({"verdict": verdict, "notes": notes},
                                ensure_ascii=False), call_id))
            if own:
                conn.commit()
        finally:
            if own:
                self.release(conn)

    # ------------------------------------------------------------------ #
    # Call attempts: guarded state machine
    # ------------------------------------------------------------------ #
    def create_attempt(self, attempt_id, call_id, provider="exolve",
                       attempt_no=1, callout_id=None, conn=None):
        self._exec(
            "INSERT INTO call_attempts "
            "(attempt_id, call_id, provider, status, attempt_no, callout_id) "
            "VALUES (%s, %s, %s, 'scheduled', %s, %s) "
            "ON CONFLICT (attempt_id) DO NOTHING",
            (attempt_id, call_id, provider, attempt_no, callout_id),
            conn=conn)

    def get_attempt(self, attempt_id):
        return self._exec(
            "SELECT * FROM call_attempts WHERE attempt_id = %s",
            (attempt_id,), fetch="one")

    def get_attempt_by_callout(self, callout_id):
        return self._exec(
            "SELECT * FROM call_attempts WHERE callout_id = %s",
            (callout_id,), fetch="one")

    def _transition(self, attempt_id, from_statuses, to_status, assigns=(),
                    conn=None):
        """Guarded status move. Returns True iff exactly one row updated."""
        clauses = ["status = %s"]
        params = [to_status]
        for col, val in assigns:
            if val is NOW:
                clauses.append(f"{col} = now()")
            else:
                clauses.append(f"{col} = %s")
                params.append(val)
        params += [attempt_id, list(from_statuses)]
        n = self._exec(
            f"UPDATE call_attempts SET {', '.join(clauses)} "
            "WHERE attempt_id = %s AND status = ANY(%s)",
            params, conn=conn)
        return n == 1

    def mark_ringing(self, attempt_id, callout_id=None, conn=None):
        return self._transition(
            attempt_id, ("scheduled",), "ringing",
            (("callout_id", callout_id),) if callout_id else (),
            conn=conn)

    def mark_answered(self, attempt_id, conn=None):
        # late answered (after completed/no_answer) → False, ignored
        return self._transition(
            attempt_id, ("ringing", "scheduled"), "answered", conn=conn)

    def mark_completed(self, attempt_id, duration_seconds=None,
                       provider_event_id=None, conn=None):
        return self._transition(
            attempt_id, ("answered", "ringing", "scheduled"), "completed",
            (("ended_at", NOW),
             ("duration_seconds", duration_seconds),
             ("provider_event_id", provider_event_id)),
            conn=conn)

    def mark_failed(self, attempt_id, cause, provider_event_id=None,
                    conn=None):
        return self._transition(
            attempt_id, ("scheduled", "ringing", "answered"), "failed",
            (("hangup_cause", cause),
             ("ended_at", NOW),
             ("provider_event_id", provider_event_id)),
            conn=conn)

    def close_attempt(self, call_id, conn=None):
        """Close the parent session when an attempt reaches a terminal state."""
        self._exec(
            "UPDATE call_sessions SET status = 'completed', ended_at = now() "
            "WHERE call_id = %s", (call_id,), conn=conn)

    # ------------------------------------------------------------------ #
    # Provider webhook inbox (idempotent)
    # ------------------------------------------------------------------ #
    def ingest_provider_event(self, event_id, kind, payload,
                              provider="exolve", call_id=None,
                              attempt_id=None):
        """True only for the FIRST sighting. A webhook replayed 100x yields
        one insert. Commits immediately (the event is durable)."""
        return self._exec(
            "INSERT INTO provider_events "
            "(event_id, provider, call_id, attempt_id, kind, payload) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (event_id) DO NOTHING RETURNING event_id",
            (event_id, provider, call_id, attempt_id, kind,
             json.dumps(payload, ensure_ascii=False)),
            fetch="val") is not None

    def mark_event_processed(self, event_id, error=None, conn=None):
        self._exec(
            "UPDATE provider_events SET processed_at = now(), "
            "processing_error = %s WHERE event_id = %s",
            (error, event_id), conn=conn)

    def event(self, event_id):
        return self._exec(
            "SELECT * FROM provider_events WHERE event_id = %s",
            (event_id,), fetch="one")

    def unprocessed_events(self, limit=100):
        return self._exec(
            "SELECT * FROM provider_events WHERE processed_at IS NULL "
            "ORDER BY received_at LIMIT %s", (limit,), fetch="all")

    # ------------------------------------------------------------------ #
    # Outbox
    # ------------------------------------------------------------------ #
    def enqueue(self, topic, payload, dedup_key=None, conn=None):
        """Enqueue a message. Idempotent per dedup_key (partial unique
        index; target-less ON CONFLICT so NULL dedup_key still inserts)."""
        return self._exec(
            "INSERT INTO outbox_messages (topic, payload, dedup_key) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT DO NOTHING RETURNING id",
            (topic, json.dumps(payload, ensure_ascii=False), dedup_key),
            fetch="val", conn=conn)

    def claim_batch(self, limit=10, worker_id="", lock_seconds=60, conn=None):
        """Atomically lease pending messages (FOR UPDATE SKIP LOCKED)."""
        return self._exec(
            "UPDATE outbox_messages SET locked_at = now(), locked_by = %s "
            "WHERE id = ANY (SELECT id FROM outbox_messages "
            "  WHERE status = 'pending' AND next_attempt_at <= now() "
            "    AND (locked_at IS NULL OR locked_at < now() - %s::interval) "
            "  ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED) "
            "RETURNING id, topic, payload, attempts",
            (worker_id, f"{lock_seconds} seconds", limit), conn=conn,
            fetch="all")
        if rows is None:
            return []

    def resolve_outbox(self, msg_id, ok, delay_seconds=0, max_attempts=10,
                       conn=None):
        """Dispatch (ok) or schedule a retry (fail). A retry returns the
        message to 'pending' (so claim_batch picks it up again) with attempts
        incremented; it dies ('dead') after max_attempts."""
        if ok:
            self._exec(
                "UPDATE outbox_messages SET status = 'dispatched', "
                "delivered_at = now(), locked_at = NULL, locked_by = NULL "
                "WHERE id = %s", (msg_id,), conn=conn)
            return "dispatched"
        self._exec(
            "UPDATE outbox_messages SET attempts = attempts + 1, "
            "locked_at = NULL, locked_by = NULL, "
            "status = CASE WHEN attempts + 1 >= %s THEN 'dead' "
            "               ELSE 'pending' END, "
            "next_attempt_at = now() + %s::interval "
            "WHERE id = %s",
            (max_attempts, f"{delay_seconds} seconds", msg_id), conn=conn)
        return "failed"

    # ------------------------------------------------------------------ #
    # Phase 3: incidents + delivery plan.

    def open_incident(self, incident_id, call_id, verdict, severity="red",
                      notes=None, escalation_level=0, conn=None):
        """Idempotent open: a replay never creates a second incident."""
        return self._exec(
            "INSERT INTO incidents (id, call_id, status, severity, notes, "
            "                        escalation_level) "
            "VALUES (%s, %s, 'open', %s, %s, %s) "
            "ON CONFLICT (id) DO NOTHING RETURNING id",
            (incident_id, call_id, severity,
             json.dumps(notes or [], ensure_ascii=False), escalation_level),
            fetch="val", conn=conn)

    def queue_action(self, incident_id, channel, contact, order_idx,
                     payload=None, conn=None):
        """Append a delivery action to the incident's escalation plan."""
        return self._exec(
            "INSERT INTO incident_actions (incident_id, channel, contact, "
            "                              order_idx, payload) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (incident_id, channel, contact, order_idx,
             json.dumps(payload or {}, ensure_ascii=False)),
            fetch="val", conn=conn)

    def get_incident(self, incident_id):
        return self._exec(
            "SELECT * FROM incidents WHERE id = %s", (incident_id,),
            fetch="one")

    def get_incident_by_call(self, call_id, statuses=("open", "ack",
                                                      "checking")):
        """Latest live incident for a call — the idempotency anchor for
        maybe_open (outbox delivery is at-least-once)."""
        return self._exec(
            "SELECT * FROM incidents WHERE call_id = %s "
            "AND status = ANY(%s) ORDER BY opened_at DESC LIMIT 1",
            (call_id, list(statuses)), fetch="one")

    def list_incidents(self, statuses=None, limit=100):
        if statuses:
            return self._exec(
                "SELECT * FROM incidents WHERE status = ANY(%s) "
                "ORDER BY opened_at DESC LIMIT %s",
                (list(statuses), limit), fetch="all")
        return self._exec(
            "SELECT * FROM incidents ORDER BY opened_at DESC LIMIT %s",
            (limit,), fetch="all")

    def get_action(self, action_id):
        return self._exec(
            "SELECT * FROM incident_actions WHERE id = %s", (action_id,),
            fetch="one")

    def actions_for(self, incident_id):
        return self._exec(
            "SELECT * FROM incident_actions WHERE incident_id = %s "
            "ORDER BY order_idx", (incident_id,), fetch="all")

    def transition_incident(self, incident_id, from_statuses, to_status,
                            actor, reason, assigns=(), conn=None):
        """Guarded transition + audit in ONE transaction (idempotent)."""
        set_sql = "status = %s, updated_at = now()"
        params = [to_status]
        for col, v in assigns:
            if v == "now()":
                set_sql += f", {col} = now()"
            else:
                set_sql += f", {col} = %s"
                params.append(v)
        sql = (
            "UPDATE incidents SET " + set_sql +
            " WHERE id = %s AND status = ANY(%s)")
        params += [incident_id, list(from_statuses)]
        n = self._exec(sql, tuple(params), conn=conn)
        if n:
            self.audit(f"incident.{to_status}", actor, "incident",
                       incident_id, {"reason": reason or "",
                                     "from": ",".join(from_statuses)},
                       conn=conn)
        return bool(n)

    def next_queued_action(self, incident_id):
        """Lowest-order action still queued for delivery."""
        return self._exec(
            "SELECT * FROM incident_actions WHERE incident_id = %s "
            "AND status = 'queued' ORDER BY order_idx LIMIT 1",
            (incident_id,), fetch="one")

    def mark_action_sent(self, action_id, detail=None, conn=None):
        self._exec(
            "UPDATE incident_actions SET status = 'sent', sent_at = now() "
            "WHERE id = %s", (action_id,), conn=conn)

    def mark_action_confirmed(self, action_id, actor, note=None, conn=None):
        self._exec(
            "UPDATE incident_actions SET status = 'confirmed', "
            "confirmed_at = now() WHERE id = %s", (action_id,), conn=conn)
        self.audit("incident.action.confirmed", actor, "incident_action",
                   action_id, {"note": note or ""}, conn=conn)

    def mark_action_failed(self, action_id, detail=None, conn=None):
        self._exec(
            "UPDATE incident_actions SET status = 'failed', attempts = "
            "attempts + 1 WHERE id = %s", (action_id,), conn=conn)

    def escalation_overdue(self, ack_seconds, resolve_seconds):
        """Incidents needing escalation: open past ack deadline (no confirmed
        action) or ack/checking past resolve deadline."""
        return self._exec(
            "SELECT * FROM incidents WHERE status = 'open' "
            "AND opened_at + (escalation_level + 1) * %s * interval '1 second' "
            "        < now() "
            "AND NOT EXISTS (SELECT 1 FROM incident_actions a "
            "                WHERE a.incident_id = incidents.id "
            "                AND a.status = 'confirmed') "
            "UNION ALL "
            "SELECT * FROM incidents WHERE status IN ('ack','checking') "
            "AND opened_at + %s * interval '1 second' < now()",
            (ack_seconds, resolve_seconds), fetch="all")

    def bump_escalation(self, incident_id, actor="system", conn=None):
        self._exec(
            "UPDATE incidents SET escalation_level = escalation_level + 1, "
            "updated_at = now() WHERE id = %s", (incident_id,), conn=conn)
        self.audit("incident.escalated", actor, "incident", incident_id,
                   conn=conn)

    # ------------------------------------------------------------------ #
    # Family app <-> call pipeline (migration 002). Auth = api_key hash;
    # authorization = account_access grants. Phones are normalized digits.
    # ------------------------------------------------------------------ #
    def family_account_by_key_hash(self, key_hash):
        """Active (non-revoked) account for an API-key sha256 hex."""
        return self._exec(
            "SELECT account_id, display_name, role FROM family_accounts "
            "WHERE api_key_hash = %s AND revoked_at IS NULL",
            (key_hash,), fetch="one")

    def family_elder_by_phone(self, phone_digits):
        return self._exec(
            "SELECT person_id, phone, display_name FROM elders "
            "WHERE phone = %s", (phone_digits,), fetch="one")

    def family_has_access(self, account_id, person_id):
        return bool(self._exec(
            "SELECT 1 FROM account_access WHERE account_id = %s "
            "AND person_id = %s", (account_id, person_id), fetch="val"))

    def family_add_question(self, q_id, person_id, account_id, author_label,
                            text):
        self._exec(
            "INSERT INTO family_questions "
            "(q_id, person_id, author_account_id, author_label, text) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (q_id) DO NOTHING",
            (q_id, person_id, account_id, author_label, text))

    def family_pending(self, phone_digits, limit=5):
        """Pending questions for a caller's phone, oldest first. Called ONCE
        at call start (snapshot); mid-call arrivals wait for the next call."""
        rows = self._exec(
            "SELECT q.q_id, q.text, COALESCE(q.author_label, 'Родные') "
            "       AS author "
            "FROM family_questions q JOIN elders e ON e.person_id = q.person_id "
            "WHERE e.phone = %s AND q.status = 'pending' "
            "ORDER BY q.created_at LIMIT %s",
            (phone_digits, limit), fetch="all")
        return rows or []

    def family_sync_asked(self, call_id, questions):
        """Persist per-call question outcomes after the turn/call. Only rows
        still 'pending' are moved — replay-safe."""
        n = 0
        for q in questions or []:
            if q.get("status") != "asked":
                continue
            n += self._exec(
                "UPDATE family_questions SET status = 'asked', "
                "asked_call_id = %s, answer_text = %s, answered_at = now() "
                "WHERE q_id = %s AND status = 'pending'",
                (call_id, q.get("answer"), q.get("id")))
        return n

    def family_list(self, phone_digits, limit=50):
        """Question history for the app's polling endpoint (newest first)."""
        rows = self._exec(
            "SELECT q.q_id, q.text, q.status, q.author_label, q.created_at, "
            "       q.asked_call_id, q.answer_text, q.answered_at "
            "FROM family_questions q JOIN elders e "
            "     ON e.person_id = q.person_id "
            "WHERE e.phone = %s ORDER BY q.created_at DESC LIMIT %s",
            (phone_digits, limit), fetch="all")
        return rows or []


def maybe_pg_store(url=None, check=True):
    """Build a PgStore when configured, else a loud stand-in (_NoPg).

    A configured-but-unreachable Postgres NEVER silently downgrades: it is
    reported loudly on stdout and the caller surfaces it in /health.
    """
    url = _default_url() if url is None else url
    if not url:
        print("[pg] MOSS_PG_URL unset — file/offline mode", flush=True)
        return _NO_PG
    try:
        store = PgStore(url=url)
        if check:
            store.ping()
        print(f"[pg] connected: {type(store).__name__}", flush=True)
        return store
    except Exception as e:  # noqa: BLE001
        print(f"[pg] UNAVAILABLE ({e}) — continuing WITHOUT durable state; "
              f"surfaced in /health", flush=True)
        return _NO_PG