-- Phase 12: performance indexes for large networks

CREATE INDEX IF NOT EXISTS idx_topology_links_snapshot
    ON topology_links(snapshot_id);

CREATE INDEX IF NOT EXISTS idx_topology_links_network
    ON topology_links(network_id, snapshot_id);

CREATE INDEX IF NOT EXISTS idx_ha_enrichment_network
    ON ha_device_enrichment(network_id);

CREATE INDEX IF NOT EXISTS idx_events_network_type_time
    ON events(network_id, event_type, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_incident_devices_network
    ON incident_devices(network_id, ieee_address);
