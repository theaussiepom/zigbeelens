-- Track 6: expression indexes for absolute-time retention selectors.
-- Portable julianday(...) indexes support coarse absolute-time range scans on
-- SQLite versions shipped with CPython 3.11+ (no fractional unixepoch modifier).
-- Exact eligibility uses retention_instant() (registered by Core) with
-- microsecond precision. No data rewrite.

CREATE INDEX IF NOT EXISTS idx_metric_samples_retention
  ON metric_samples (julianday(sampled_at), id);

CREATE INDEX IF NOT EXISTS idx_availability_changes_retention
  ON availability_changes (julianday(changed_at), id);

CREATE INDEX IF NOT EXISTS idx_device_snapshots_retention
  ON device_snapshots (julianday(captured_at), id);

CREATE INDEX IF NOT EXISTS idx_bridge_snapshots_retention
  ON bridge_snapshots (julianday(captured_at), id);

CREATE INDEX IF NOT EXISTS idx_health_snapshots_retention
  ON health_snapshots (julianday(captured_at), id);

CREATE INDEX IF NOT EXISTS idx_unresolved_device_messages_retention
  ON unresolved_device_messages (julianday(received_at), id);

CREATE INDEX IF NOT EXISTS idx_events_retention
  ON events (julianday(occurred_at), id);

CREATE INDEX IF NOT EXISTS idx_reports_retention
  ON reports (julianday(generated_at), id);

CREATE INDEX IF NOT EXISTS idx_incidents_resolved_retention
  ON incidents (julianday(resolved_at), id)
  WHERE lifecycle_state = 'resolved' AND resolved_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_topology_snapshots_retention
  ON topology_snapshots (status, julianday(captured_at), snapshot_id);

-- events(incident_id) already exists as idx_events_incident (migration 009).

-- Terminal topology history for age retention (global oldest-first).
CREATE INDEX IF NOT EXISTS idx_topology_terminal_age
  ON topology_snapshots (julianday(captured_at), snapshot_id)
  WHERE status IN ('complete', 'error');

-- Terminal topology history for per-network count-cap windows.
CREATE INDEX IF NOT EXISTS idx_topology_terminal_history
  ON topology_snapshots (network_id, julianday(captured_at), snapshot_id)
  WHERE status IN ('complete', 'error');
