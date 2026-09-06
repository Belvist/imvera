-- IMVERA VoiseUp persistence v1
-- Apply: python3 scripts/migrate.py

CREATE TABLE IF NOT EXISTS call_results (
    call_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL,
    fsm_state TEXT NOT NULL,
    facts JSONB NOT NULL DEFAULT '{}',
    fact_quotes JSONB NOT NULL DEFAULT '{}',
    observations JSONB NOT NULL DEFAULT '[]',
    delivery_stage TEXT NOT NULL DEFAULT 'OBSERVATION_RECEIVED',
    partial BOOLEAN NOT NULL DEFAULT TRUE,
    call_ended BOOLEAN NOT NULL DEFAULT FALSE,
    termination_reason TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS call_observations (
    observation_id TEXT PRIMARY KEY,
    call_id TEXT NOT NULL REFERENCES call_results(call_id),
    family_id TEXT NOT NULL,
    turn_id INT NOT NULL,
    field TEXT,
    value TEXT NOT NULL,
    source_quote TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT 'elder',
    negated BOOLEAN NOT NULL DEFAULT FALSE,
    risk_level TEXT NOT NULL DEFAULT 'NONE',
    episode_id TEXT,
    idempotency_key TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS call_events (
    event_id TEXT PRIMARY KEY,
    call_id TEXT NOT NULL,
    family_id TEXT NOT NULL,
    sequence_no INT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    idempotency_key TEXT UNIQUE NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outbox (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT UNIQUE NOT NULL,
    call_id TEXT NOT NULL,
    family_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_call_results_family ON call_results(family_id);
CREATE INDEX IF NOT EXISTS idx_call_observations_call ON call_observations(call_id);
CREATE INDEX IF NOT EXISTS idx_call_events_call ON call_events(call_id);
