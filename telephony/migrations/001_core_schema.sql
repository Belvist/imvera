-- MossVoice data core — Phase 2 schema (idempotent by design).
-- Every statement is safe to re-run: CREATE ... IF NOT EXISTS.
-- Version tracking lives in schema_migrations (core/migrate.py).

CREATE TABLE IF NOT EXISTS schema_migrations (
    version      TEXT PRIMARY KEY,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------ #
-- Calls (authoritative business truth; replaces the file Recorder).
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS call_sessions (
    call_id        TEXT PRIMARY KEY,
    caller_id      TEXT,
    consent_id     TEXT,
    status         TEXT NOT NULL DEFAULT 'active',   -- active | completed | failed | expired
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at       TIMESTAMPTZ,
    retention_days INTEGER DEFAULT 90,
    result         JSONB
);

-- ------------------------------------------------------------------ #
-- Dial-out attempts (one call_session can have several).
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS call_attempts (
    attempt_id        TEXT PRIMARY KEY,
    call_id           TEXT NOT NULL REFERENCES call_sessions(call_id) ON DELETE CASCADE,
    provider          TEXT NOT NULL DEFAULT 'exolve',
    status            TEXT NOT NULL DEFAULT 'scheduled',
                      -- scheduled | ringing | answered | completed
                      -- | no_answer | timeout | failed | canceled
    attempt_no        INTEGER NOT NULL DEFAULT 1,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    answered_at       TIMESTAMPTZ,
    ended_at          TIMESTAMPTZ,
    duration_seconds  INTEGER,
    hangup_cause      TEXT,
    callout_id        TEXT,                  -- provider's outbound-call id (idempotency)
    provider_event_id TEXT,                  -- the provider event that ended this attempt
    UNIQUE (callout_id)
);

CREATE INDEX IF NOT EXISTS idx_attempts_call
    ON call_attempts (call_id, status);

-- ------------------------------------------------------------------ #
-- Dialogue turns (per-turn transcript + STT confidence).
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS dialogue_turns (
    turn_id     BIGSERIAL PRIMARY KEY,
    call_id     TEXT NOT NULL REFERENCES call_sessions(call_id) ON DELETE CASCADE,
    role        TEXT NOT NULL,               -- user | assistant
    text        TEXT,
    source      TEXT NOT NULL DEFAULT 'stt', -- stt | scripted | llm
    confidence  REAL,                        -- 0..1 | NULL
    audio_key   TEXT,                        -- MinIO object key | NULL
    ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_turns_call ON dialogue_turns (call_id);

-- ------------------------------------------------------------------ #
-- Layer-A questionnaire answers (check-in).
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS dialogue_answers (
    id       BIGSERIAL PRIMARY KEY,
    call_id  TEXT NOT NULL REFERENCES call_sessions(call_id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer   TEXT NOT NULL,
    ts       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------ #
-- Final verdict of the call.
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS call_results (
    call_id     TEXT PRIMARY KEY REFERENCES call_sessions(call_id) ON DELETE CASCADE,
    verdict     TEXT NOT NULL,               -- ok | attention | alert | no_speech | unknown
    confidence  REAL,
    notes       JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------ #
-- Provider webhook inbox (idempotency: PK == provider's event id).
-- A webhook replayed 100x inserts 0 rows after the first — 1 processing.
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS provider_events (
    event_id           TEXT PRIMARY KEY,
    provider           TEXT NOT NULL DEFAULT 'exolve',
    call_id            TEXT,
    attempt_id         TEXT,
    kind               TEXT NOT NULL,        -- call_started|answered|completed|failed|...
    payload            JSONB NOT NULL DEFAULT '{}'::jsonb,
    received_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at       TIMESTAMPTZ,
    processing_error   TEXT
);

-- ------------------------------------------------------------------ #
-- Transactional outbox (written in the SAME tx as the business record).
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS outbox_messages (
    id              BIGSERIAL PRIMARY KEY,
    topic           TEXT NOT NULL,           -- incident.notify | call.result | ...
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    dedup_key       TEXT,                    -- idempotent re-enqueue (reprocessing)
    status          TEXT NOT NULL DEFAULT 'pending',
                    -- pending | dispatched | failed | dead
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_at       TIMESTAMPTZ,
    locked_by       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON outbox_messages (status) WHERE status = 'pending';

CREATE UNIQUE INDEX IF NOT EXISTS idx_outbox_dedup
    ON outbox_messages (dedup_key) WHERE dedup_key IS NOT NULL;

-- ------------------------------------------------------------------ #
-- Incidents & escalation actions ("notified != resolved").
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS incidents (
    id          TEXT PRIMARY KEY,
    call_id     TEXT REFERENCES call_sessions(call_id),
    status      TEXT NOT NULL DEFAULT 'open',
                -- open | ack | checking | resolved | false_alarm
    severity    TEXT NOT NULL DEFAULT 'red',
    actor       TEXT,
    reason      TEXT,
    notes       JSONB NOT NULL DEFAULT '[]'::jsonb,
    opened_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_incidents_status
    ON incidents (status) WHERE status IN ('open', 'ack', 'checking');

CREATE TABLE IF NOT EXISTS incident_actions (
    id           BIGSERIAL PRIMARY KEY,
    incident_id  TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    channel      TEXT NOT NULL,              -- telegram | sms | call | email
    contact      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'queued',
                 -- queued | sent | confirmed | failed
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at      TIMESTAMPTZ,
    confirmed_at TIMESTAMPTZ
);

-- ------------------------------------------------------------------ #
-- Consent (voice + written), retention drives audio lifetime.
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS consents (
    id           TEXT PRIMARY KEY,
    person_id    TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'voice',   -- voice | written
    scope        JSONB NOT NULL DEFAULT '{}'::jsonb,
    granted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_consents_person ON consents (person_id, revoked_at);

-- ------------------------------------------------------------------ #
-- Long-term memory + audit.
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS person_memory (
    person_id  TEXT NOT NULL,
    mem_key    TEXT NOT NULL,
    value      JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (person_id, mem_key)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         BIGSERIAL PRIMARY KEY,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    entity     TEXT,
    entity_id  TEXT,
    detail     JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_audit_entity
    ON audit_log (entity, entity_id);