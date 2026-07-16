-- Track 3D: indexes for scoped event queries and bulk incident-device lookups

CREATE INDEX IF NOT EXISTS idx_events_device
ON events(network_id, ieee_address, occurred_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_events_incident
ON events(incident_id, occurred_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_incident_devices_device
ON incident_devices(network_id, ieee_address, incident_id);
