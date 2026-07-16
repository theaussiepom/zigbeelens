-- Track 3E: expression index matching collection ORDER BY lifecycle rank.
-- Matches:
--   CASE lifecycle_state WHEN 'open' THEN 0 WHEN 'watching' THEN 1 ELSE 2 END ASC,
--   updated_at DESC, id DESC
-- Keep idx_incidents_lifecycle (004) for COUNT / lifecycle filtering.

CREATE INDEX IF NOT EXISTS idx_incidents_collection_order
  ON incidents (
    (CASE lifecycle_state WHEN 'open' THEN 0 WHEN 'watching' THEN 1 ELSE 2 END),
    updated_at DESC,
    id DESC
  );
