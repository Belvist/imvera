-- Product Core (ROADMAP Э4) — households, schedules, call jobs, device tokens.
-- Idempotent: CREATE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS.

-- ------------------------------------------------------------------ #
-- Family app users (OTP/JWT auth). Separate from legacy family_accounts.
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    phone       TEXT UNIQUE,
    phone_hash  TEXT,
    name        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_phone_hash
    ON users (phone_hash) WHERE phone_hash IS NOT NULL;

-- ------------------------------------------------------------------ #
-- Households (one family unit; owner + members + viewers).
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS households (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    owner_user_id TEXT REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS household_members (
    household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role         TEXT NOT NULL
                 CHECK (role IN ('owner', 'member', 'viewer')),
    PRIMARY KEY (household_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_household_members_user
    ON household_members (user_id);

-- ------------------------------------------------------------------ #
-- Elder profile extensions (base table from 003_family_questions).
-- ------------------------------------------------------------------ #
ALTER TABLE elders ADD COLUMN IF NOT EXISTS timezone TEXT;
ALTER TABLE elders ADD COLUMN IF NOT EXISTS display_name TEXT;
ALTER TABLE elders ADD COLUMN IF NOT EXISTS speech_notes TEXT;
ALTER TABLE elders ADD COLUMN IF NOT EXISTS call_goal TEXT;
ALTER TABLE elders ADD COLUMN IF NOT EXISTS household_id TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'elders_household_id_fkey'
    ) THEN
        ALTER TABLE elders
            ADD CONSTRAINT elders_household_id_fkey
            FOREIGN KEY (household_id) REFERENCES households(id)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_elders_household
    ON elders (household_id) WHERE household_id IS NOT NULL;

-- ------------------------------------------------------------------ #
-- Escalation contacts (ordered channels per household / elder).
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS contacts (
    id             TEXT PRIMARY KEY,
    household_id   TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    elder_id       TEXT REFERENCES elders(person_id) ON DELETE CASCADE,
    user_id        TEXT REFERENCES users(id) ON DELETE SET NULL,
    channel        TEXT NOT NULL,          -- push | telegram | sms | call | email
    address        TEXT NOT NULL,
    escalate_order INTEGER NOT NULL DEFAULT 0,
    label          TEXT
);

CREATE INDEX IF NOT EXISTS idx_contacts_household_order
    ON contacts (household_id, escalate_order);

-- ------------------------------------------------------------------ #
-- Outbound call schedules (Э5 consumes call_jobs generated from these).
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS schedules (
    id             TEXT PRIMARY KEY,
    elder_id       TEXT NOT NULL REFERENCES elders(person_id) ON DELETE CASCADE,
    timezone       TEXT NOT NULL DEFAULT 'Europe/Moscow',
    days_of_week   INT[] NOT NULL DEFAULT '{1,2,3,4,5,6,7}',
    window_start   TIME NOT NULL DEFAULT '10:00',
    window_end     TIME NOT NULL DEFAULT '13:00',
    frequency      TEXT NOT NULL DEFAULT 'daily',
    quiet_start    TIME,
    quiet_end      TIME,
    attempt_policy JSONB NOT NULL DEFAULT
        '{"max_attempts":3,"interval_minutes":15}'::jsonb,
    paused         BOOLEAN NOT NULL DEFAULT false,
    enabled        BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (elder_id)
);

-- ------------------------------------------------------------------ #
-- APNs / FCM device tokens for family push.
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS device_tokens (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform    TEXT NOT NULL,             -- ios | android
    token       TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_device_tokens_user
    ON device_tokens (user_id) WHERE revoked_at IS NULL;

-- ------------------------------------------------------------------ #
-- Scheduled outbound call jobs (Э5 dialer lease queue).
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS call_jobs (
    id              TEXT PRIMARY KEY,
    elder_id        TEXT NOT NULL REFERENCES elders(person_id),
    schedule_id     TEXT REFERENCES schedules(id) ON DELETE SET NULL,
    due_at          TIMESTAMPTZ NOT NULL,
    attempt_no      INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending', 'claimed', 'in_progress', 'done',
                        'failed', 'no_contact', 'cancelled')),
    lease_owner     TEXT,
    lease_until     TIMESTAMPTZ,
    result_call_id  TEXT,
    last_error      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_call_jobs_status_due
    ON call_jobs (status, due_at);

CREATE INDEX IF NOT EXISTS idx_call_jobs_elder
    ON call_jobs (elder_id, due_at DESC);

-- ------------------------------------------------------------------ #
-- Tenant / household on durable call + incident contracts (§16 / Э4).
-- ------------------------------------------------------------------ #
ALTER TABLE call_sessions ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE call_sessions ADD COLUMN IF NOT EXISTS household_id TEXT;

CREATE INDEX IF NOT EXISTS idx_call_sessions_household
    ON call_sessions (household_id) WHERE household_id IS NOT NULL;

ALTER TABLE incidents ADD COLUMN IF NOT EXISTS household_id TEXT;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS elder_id TEXT;

CREATE INDEX IF NOT EXISTS idx_incidents_household
    ON incidents (household_id, opened_at DESC)
    WHERE household_id IS NOT NULL;
