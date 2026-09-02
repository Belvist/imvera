-- ROADMAP E2: family-facing call status columns on call_results.
-- Idempotent: ADD COLUMN IF NOT EXISTS.

ALTER TABLE call_results ADD COLUMN IF NOT EXISTS family_status TEXT;
ALTER TABLE call_results ADD COLUMN IF NOT EXISTS reasons JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE call_results ADD COLUMN IF NOT EXISTS summary_for_family TEXT;
ALTER TABLE call_results ADD COLUMN IF NOT EXISTS scenario_version TEXT;
ALTER TABLE call_results ADD COLUMN IF NOT EXISTS safety_rules_version TEXT;
ALTER TABLE call_results ADD COLUMN IF NOT EXISTS technical_error TEXT;
