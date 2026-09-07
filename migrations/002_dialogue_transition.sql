-- Dialogue mid-call state: ledger + outbox (IMVERA 2026-09-07 Stage 1)

ALTER TABLE call_results ADD COLUMN IF NOT EXISTS state_version INT NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS question_goals (
    call_id TEXT NOT NULL REFERENCES call_results(call_id),
    semantic_key TEXT NOT NULL,
    goal_id TEXT NOT NULL,
    topic_slot TEXT NOT NULL,
    status TEXT NOT NULL,
    automatic_attempts_used INT NOT NULL DEFAULT 0,
    max_automatic_attempts INT NOT NULL DEFAULT 2,
    reserved_attempt_id TEXT,
    last_question_id TEXT,
    last_delivery_state TEXT NOT NULL DEFAULT 'unknown',
    audio_may_have_reached_channel BOOLEAN NOT NULL DEFAULT FALSE,
    goal_json JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (call_id, semantic_key)
);

CREATE TABLE IF NOT EXISTS action_outbox (
    action_id TEXT PRIMARY KEY,
    call_id TEXT NOT NULL REFERENCES call_results(call_id),
    family_id TEXT NOT NULL,
    turn_id INT NOT NULL,
    intent TEXT NOT NULL,
    speech TEXT NOT NULL,
    question_goal_id TEXT,
    state_version INT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_question_goals_call ON question_goals(call_id);
CREATE INDEX IF NOT EXISTS idx_action_outbox_call ON action_outbox(call_id);
