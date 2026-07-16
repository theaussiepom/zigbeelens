-- Track 3E: keyset pagination on lifecycle + updated_at + id.
-- Justified by EXPLAIN QUERY PLAN on filtered/paginated incident collection reads.

CREATE INDEX IF NOT EXISTS idx_incidents_lifecycle_updated_id
  ON incidents (lifecycle_state, updated_at DESC, id DESC);
