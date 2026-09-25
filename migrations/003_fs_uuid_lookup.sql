-- Stage 0 slice 1: index for get_call_binding_by_fs_uuid (was Seq Scan).
-- Expression btree matches the exact query predicate in
-- packages/core/pg_store.py:get_call_binding_by_fs_uuid.

CREATE INDEX IF NOT EXISTS idx_call_results_fs_uuid
    ON call_results ((metadata #>> '{product_call_binding,metadata,fs_uuid}'));
