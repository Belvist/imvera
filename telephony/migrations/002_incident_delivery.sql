-- ------------------------------------------------------------------ #
-- Phase 3: Incident Engine + delivery.
-- Adds escalation bookkeeping to incidents / incident_actions.
-- Idempotent: ALTER TABLE ... ADD COLUMN IF NOT EXISTS.
-- ------------------------------------------------------------------ #

ALTER TABLE incidents ADD COLUMN IF NOT EXISTS escalation_level
    INTEGER NOT NULL DEFAULT 0;

ALTER TABLE incidents ADD COLUMN IF NOT EXISTS updated_at
    TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE incidents ADD COLUMN IF NOT EXISTS confirm_deadline
    TIMESTAMPTZ;

ALTER TABLE incident_actions ADD COLUMN IF NOT EXISTS order_idx
    INTEGER NOT NULL DEFAULT 0;

ALTER TABLE incident_actions ADD COLUMN IF NOT EXISTS attempts
    INTEGER NOT NULL DEFAULT 0;

ALTER TABLE incident_actions ADD COLUMN IF NOT EXISTS next_attempt_at
    TIMESTAMPTZ NOT NULL DEFAULT now();