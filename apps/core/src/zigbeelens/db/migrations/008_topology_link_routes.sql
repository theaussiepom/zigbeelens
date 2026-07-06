-- Route-table evidence on topology links.
--
-- Zigbee2MQTT raw network maps attach a `routes` array to each link,
-- containing the source device's routing-table entries whose next hop is the
-- link target. `route_count` records how many such entries were reported.
-- NULL means the payload carried no routes information for the link (unknown),
-- which is distinct from an observed zero.
ALTER TABLE topology_links ADD COLUMN route_count INTEGER;
