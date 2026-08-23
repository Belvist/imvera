-- Family app <-> call pipeline (2026-08-23, owner-approved skeleton).
-- The iPhone app authenticates with a per-account API key, writes questions
-- for an elder's phone number; Vera asks them during the next call and the
-- answers flow back through GET /family/questions + call.result notes.
-- Idempotent by design: every statement is safe to re-run.

-- ------------------------------------------------------------------ #
-- Elders: the phone number is the join key for the whole pipeline.
-- phone is NORMALIZED DIGITS ONLY (no +, spaces or dashes) — Lua/FS
-- caller_id formats vary, matching must not depend on formatting.
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS elders (
    person_id    TEXT PRIMARY KEY,
    phone        TEXT NOT NULL UNIQUE,          -- normalized digits
    display_name TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------ #
-- Family accounts (app users: son, daughter, in-law...). The API key is
-- generated server-side, shown ONCE, stored as sha256 hex. Rotation =
-- new row version via revoked_at (old key stops working immediately).
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS family_accounts (
    account_id   TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    role         TEXT,
    api_key_hash TEXT NOT NULL UNIQUE,
    revoked_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------ #
-- Access grants: which account may ask about which elder (M:N). A key
-- alone authenticates; this table AUTHORIZES — a leaked daughter key
-- must not read another family's questions.
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS account_access (
    account_id TEXT NOT NULL REFERENCES family_accounts(account_id)
               ON DELETE CASCADE,
    person_id  TEXT NOT NULL REFERENCES elders(person_id)
               ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, person_id)
);

-- ------------------------------------------------------------------ #
-- Questions from the family. Lifecycle: pending -> asked (with answer
-- snapshot) | expired. A question is snapshotted into a call at its
-- start; mid-call arrivals wait for the NEXT call (deterministic turn).
-- ------------------------------------------------------------------ #
CREATE TABLE IF NOT EXISTS family_questions (
    q_id              TEXT PRIMARY KEY,
    person_id         TEXT NOT NULL REFERENCES elders(person_id)
                      ON DELETE CASCADE,
    author_account_id TEXT REFERENCES family_accounts(account_id),
    author_label      TEXT,                    -- "дочь", "сын"... (display)
    text              TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
                      -- pending | asked | expired
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    asked_call_id     TEXT,
    answer_text       TEXT,
    answered_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_family_questions_pending
    ON family_questions (person_id, created_at) WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_family_questions_person
    ON family_questions (person_id, created_at);
