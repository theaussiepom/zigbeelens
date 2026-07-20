-- Track 6: expression indexes for absolute-time retention selectors.
-- Native unixepoch(..., 'subsec') indexes support coarse absolute-time range
-- scans. Exact eligibility uses retention_instant() (registered by Core) with
-- microsecond precision. No data rewrite.

CREATE INDEX IF NOT EXISTS idx_metric_samples_retention
  ON metric_samples (unixepoch(sampled_at, 'subsec'), id);

CREATE INDEX IF NOT EXISTS idx_availability_changes_retention
  ON availability_changes (unixepoch(changed_at, 'subsec'), id);

CREATE INDEX IF NOT EXISTS idx_device_snapshots_retention
  ON device_snapshots (unixepoch(captured_at, 'subsec'), id);

CREATE INDEX IF NOT EXISTS idx_bridge_snapshots_retention
  ON bridge_snapshots (unixepoch(captured_at, 'subsec'), id);

CREATE INDEX IF NOT EXISTS idx_health_snapshots_retention
  ON health_snapshots (unixepoch(captured_at, 'subsec'), id);

CREATE INDEX IF NOT EXISTS idx_unresolved_device_messages_retention
  ON unresolved_device_messages (unixepoch(received_at, 'subsec'), id);

CREATE INDEX IF NOT EXISTS idx_events_retention
  ON events (unixepoch(occurred_at, 'subsec'), id);

CREATE INDEX IF NOT EXISTS idx_reports_retention
  ON reports (unixepoch(generated_at, 'subsec'), id);

CREATE INDEX IF NOT EXISTS idx_incidents_resolved_retention
  ON incidents (unixepoch(resolved_at, 'subsec'), id)
  WHERE lifecycle_state = 'resolved' AND resolved_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_topology_snapshots_retention
  ON topology_snapshots (status, unixepoch(captured_at, 'subsec'), snapshot_id);

-- events(incident_id) already exists as idx_events_incident (migration 009).

-- Terminal topology history for age/count retention selectors.
CREATE INDEX IF NOT EXISTS idx_topology_terminal_history
  ON topology_snapshots (network_id, unixepoch(captured_at, 'subsec'), snapshot_id)
  WHERE status IN ('complete', 'error');
