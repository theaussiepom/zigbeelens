-- Phase 4: incident correlation deduplication

ALTER TABLE incidents ADD COLUMN dedup_key TEXT;

CREATE INDEX IF NOT EXISTS idx_incidents_dedup ON incidents(dedup_key, lifecycle_state);
CREATE INDEX IF NOT EXISTS idx_incidents_lifecycle ON incidents(lifecycle_state, updated_at DESC);
