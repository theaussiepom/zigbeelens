-- Track 3F: factual incident ↔ network association for report scoping.
-- Lifecycle writes maintain this table; migration backfills proven identities only.

CREATE TABLE IF NOT EXISTS incident_networks (
    incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    network_id TEXT NOT NULL,
    PRIMARY KEY (incident_id, network_id)
);

CREATE INDEX IF NOT EXISTS idx_incident_networks_network
  ON incident_networks(network_id, incident_id);

-- Exact identity from incident membership rows.
INSERT OR IGNORE INTO incident_networks (incident_id, network_id)
SELECT DISTINCT incident_id, network_id
FROM incident_devices;

-- Exact single-network dedup_key forms: "{incident_type}:{network_id}"
-- Join networks.id with equality so a prefix network cannot match another.
INSERT OR IGNORE INTO incident_networks (incident_id, network_id)
SELECT i.id, n.id
FROM incidents i
JOIN networks n
  ON i.dedup_key = i.incident_type || ':' || n.id
WHERE i.incident_type IN (
    'bridge_offline',
    'network_wide_instability',
    'correlated_device_unavailability',
    'stale_reporting_cluster',
    'low_battery_cluster',
    'interview_failure',
    'unknown_pattern'
);

-- Exact device-scoped forms: "{incident_type}:{network_id}:{ieee}"
INSERT OR IGNORE INTO incident_networks (incident_id, network_id)
SELECT i.id, n.id
FROM incidents i
JOIN networks n
  ON i.dedup_key LIKE i.incident_type || ':' || n.id || ':%'
 AND substr(
       i.dedup_key,
       length(i.incident_type) + 2,
       length(n.id)
     ) = n.id
 AND substr(
       i.dedup_key,
       length(i.incident_type) + 2 + length(n.id),
       1
     ) = ':'
WHERE i.incident_type IN (
    'single_device_unavailable',
    'router_risk'
);
