-- ZigbeeLens initial schema (Phase 1)

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS networks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_topic TEXT NOT NULL,
    bridge_state TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bridge_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    network_id TEXT NOT NULL REFERENCES networks(id) ON DELETE CASCADE,
    bridge_state TEXT,
    coordinator_ieee TEXT,
    channel INTEGER,
    pan_id TEXT,
    extended_pan_id TEXT,
    payload_json TEXT,
    captured_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bridge_snapshots_network ON bridge_snapshots(network_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS devices (
    network_id TEXT NOT NULL,
    ieee_address TEXT NOT NULL,
    friendly_name TEXT NOT NULL,
    device_type TEXT NOT NULL DEFAULT 'Unknown',
    power_source TEXT NOT NULL DEFAULT 'Unknown',
    manufacturer TEXT,
    model TEXT,
    interview_state TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (network_id, ieee_address)
);

CREATE INDEX IF NOT EXISTS idx_devices_friendly_name ON devices(network_id, friendly_name);

CREATE TABLE IF NOT EXISTS device_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    network_id TEXT NOT NULL,
    ieee_address TEXT NOT NULL,
    availability TEXT,
    last_seen TEXT,
    last_payload_at TEXT,
    linkquality INTEGER,
    battery INTEGER,
    payload_json TEXT,
    captured_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (network_id, ieee_address) REFERENCES devices(network_id, ieee_address) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_device_snapshots_device ON device_snapshots(network_id, ieee_address, captured_at DESC);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    network_id TEXT,
    ieee_address TEXT,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'watch',
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    incident_id TEXT,
    payload_json TEXT,
    occurred_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_occurred ON events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_network ON events(network_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS metric_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    network_id TEXT NOT NULL,
    ieee_address TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    sampled_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_metric_samples_device ON metric_samples(network_id, ieee_address, metric_name, sampled_at DESC);

CREATE TABLE IF NOT EXISTS availability_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    network_id TEXT NOT NULL,
    ieee_address TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    changed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_availability_changes_device ON availability_changes(network_id, ieee_address, changed_at DESC);

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    incident_type TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL,
    severity TEXT NOT NULL,
    scope TEXT NOT NULL,
    confidence TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    explanation TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    counter_evidence_json TEXT NOT NULL DEFAULT '[]',
    limitations_json TEXT NOT NULL DEFAULT '[]',
    opened_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS incident_devices (
    incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    network_id TEXT NOT NULL,
    ieee_address TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'affected',
    PRIMARY KEY (incident_id, network_id, ieee_address)
);

CREATE TABLE IF NOT EXISTS health_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    network_id TEXT,
    ieee_address TEXT,
    primary_health TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    limitations_json TEXT NOT NULL DEFAULT '[]',
    captured_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    format TEXT NOT NULL,
    redaction_json TEXT NOT NULL DEFAULT '{}',
    summary TEXT NOT NULL,
    body_json TEXT,
    body_markdown TEXT,
    generated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
