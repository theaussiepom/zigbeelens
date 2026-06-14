CREATE TABLE IF NOT EXISTS topology_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    network_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL,
    raw_redacted_json TEXT,
    parsed_json TEXT,
    router_count INTEGER NOT NULL DEFAULT 0,
    end_device_count INTEGER NOT NULL DEFAULT 0,
    link_count INTEGER NOT NULL DEFAULT 0,
    warning_acknowledged INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    FOREIGN KEY (network_id) REFERENCES networks(id)
);

CREATE INDEX IF NOT EXISTS idx_topology_snapshots_network
    ON topology_snapshots(network_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS topology_nodes (
    snapshot_id TEXT NOT NULL,
    network_id TEXT NOT NULL,
    ieee_address TEXT NOT NULL,
    friendly_name TEXT,
    node_type TEXT NOT NULL,
    depth INTEGER,
    lqi INTEGER,
    raw_json TEXT,
    PRIMARY KEY (snapshot_id, ieee_address),
    FOREIGN KEY (snapshot_id) REFERENCES topology_snapshots(snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_topology_nodes_network
    ON topology_nodes(network_id, ieee_address);

CREATE TABLE IF NOT EXISTS topology_links (
    snapshot_id TEXT NOT NULL,
    network_id TEXT NOT NULL,
    source_ieee TEXT NOT NULL,
    target_ieee TEXT NOT NULL,
    source_type TEXT,
    target_type TEXT,
    linkquality INTEGER,
    depth INTEGER,
    relationship TEXT,
    raw_json TEXT,
    PRIMARY KEY (snapshot_id, source_ieee, target_ieee),
    FOREIGN KEY (snapshot_id) REFERENCES topology_snapshots(snapshot_id)
);

CREATE TABLE IF NOT EXISTS ha_enrichment_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0,
    last_push_at TEXT,
    matched_devices INTEGER NOT NULL DEFAULT 0,
    source TEXT
);

INSERT OR IGNORE INTO ha_enrichment_status (id, enabled, matched_devices) VALUES (1, 0, 0);

CREATE TABLE IF NOT EXISTS ha_device_enrichment (
    network_id TEXT NOT NULL,
    ieee_address TEXT NOT NULL,
    ha_device_id TEXT,
    ha_device_name TEXT,
    area_id TEXT,
    area_name TEXT,
    entity_id TEXT,
    match_confidence TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (network_id, ieee_address)
);
