-- ROADMAP E3: consent proof columns (voice/dtmf/written + audio hash).
-- Idempotent: ADD COLUMN IF NOT EXISTS.

ALTER TABLE consents ADD COLUMN IF NOT EXISTS method TEXT;
ALTER TABLE consents ADD COLUMN IF NOT EXISTS proof_audio_key TEXT;
ALTER TABLE consents ADD COLUMN IF NOT EXISTS proof_hash TEXT;
ALTER TABLE consents ADD COLUMN IF NOT EXISTS script_version TEXT;
ALTER TABLE consents ADD COLUMN IF NOT EXISTS household_id TEXT;

-- Backfill method from legacy kind when unset (voice|written).
UPDATE consents SET method = kind
 WHERE method IS NULL AND kind IS NOT NULL;
