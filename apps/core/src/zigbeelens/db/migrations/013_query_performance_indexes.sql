-- Phase 7A: index-only query-performance indexes.
-- Portable CREATE INDEX IF NOT EXISTS; no data rewrite / table rebuild.
-- Compatible with SQLite 3.34.1+.
--
-- Rejected candidates (not selected by production EXPLAIN):
--   idx_topology_links_snapshot_source — PK (snapshot_id, source_ieee, target_ieee)
--     already covers source lookups via sqlite_autoindex_topology_links_1
--   idx_topology_links_snapshot_target — planner prefers PK prefix on snapshot_id
--     for target lookups; INDEXED BY proves the candidate works but is unused

-- Recent-order incident first page / cursor / updated_after scans.
CREATE INDEX IF NOT EXISTS idx_incidents_recent_order
  ON incidents (updated_at DESC, id DESC);

-- Latest complete topology snapshot per network (status + captured_at).
CREATE INDEX IF NOT EXISTS idx_topology_snapshots_latest_complete
  ON topology_snapshots (network_id, status, captured_at DESC, snapshot_id DESC);

-- Mixed-metric newest-N window for one device (no metric_name predicate).
CREATE INDEX IF NOT EXISTS idx_metric_samples_device_time
  ON metric_samples (network_id, ieee_address, sampled_at DESC, id DESC);

-- Offline-transition lookback for shared-availability grouping.
CREATE INDEX IF NOT EXISTS idx_availability_changes_offline_since
  ON availability_changes (network_id, to_state, changed_at ASC, ieee_address ASC);
