-- Remove original Zigbee2MQTT map dictionaries retained by schema 006.
-- Typed topology facts remain in their dedicated columns. The already-redacted
-- capture remains the only retained source-shaped evidence.
UPDATE topology_nodes
SET raw_json = '{}';

UPDATE topology_links
SET raw_json = '{}';

-- Counts already live in typed columns. No production reader needs the
-- duplicate parsed document, so remove it instead of retaining another raw
-- JSON surface.
UPDATE topology_snapshots
SET parsed_json = NULL;
