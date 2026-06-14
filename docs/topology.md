# Topology snapshots

ZigbeeLens can optionally capture **point-in-time Zigbee2MQTT network map snapshots** to enrich router risk and incident context. Topology is never required for core diagnostics to work.

## What topology snapshots do

- Ask Zigbee2MQTT for a network map via the single allowed request topic: `{base_topic}/bridge/request/networkmap`
- Store a redacted snapshot with nodes, links, and counts
- Enrich router risk and correlated incident evidence
- Show snapshot status in the Topology page and Settings

## Why they are optional

Network map requests can temporarily make a Zigbee network less responsive, especially on larger networks. ZigbeeLens therefore:

- Disables topology by default
- Requires explicit user confirmation before manual capture
- Does not capture on startup, on incidents, or on a schedule unless explicitly enabled

## What ZigbeeLens can infer

- Possible shared router/segment patterns in a snapshot
- Topology evidence for incident context
- Router risk enrichment (linked device counts)

Language uses correlation, not certainty:

- "Latest topology snapshot **suggests**…"
- "This is **consistent with**…"

## What ZigbeeLens cannot infer

- Guaranteed current route
- Root cause
- RF interference proof
- Permanent parent-child relationships

Every topology-derived conclusion includes:

> Topology is a point-in-time snapshot and may not reflect current routing.

## Configuration

Both feature flags and topology settings must be enabled for manual capture:

```yaml
features:
  manual_network_map: true
  automatic_network_map: false

topology:
  enabled: true
  manual_capture_enabled: true
  automatic_capture_enabled: false
  capture_on_incident: false
  max_snapshots_per_network: 5
  warn_before_capture: true
```

Defaults in add-on and Docker examples keep all topology capture **disabled**.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/topology` | Overview per network |
| GET | `/api/topology/{network_id}` | Latest snapshot nodes/links |
| GET | `/api/topology/{network_id}/snapshots` | History |
| POST | `/api/topology/{network_id}/capture` | Manual capture (`confirmed: true` required) |

## Home Assistant enrichment

Optional HA area/device mapping can be pushed to Core:

| Method | Path |
|--------|------|
| GET | `/api/enrichment/status` |
| POST | `/api/enrichment/homeassistant` |
| DELETE | `/api/enrichment/homeassistant` |

The HACS integration can push redacted registry mappings when `enable_home_assistant_enrichment` is enabled. Core still works fully without HA enrichment.

Matching confidence:

- **high** — IEEE address match
- **medium** — friendly name match within network
- **low** — heuristics only; not used for strong conclusions

## Safety

- Only `{base_topic}/bridge/request/networkmap` is allowlisted for Zigbee2MQTT requests
- Collector remains subscribe-only
- No permit join, remove, reset, configure, bind, OTA, or channel changes
- Manual capture shows a clear warning in UI and API

See also [HACS integration](hacs.md) and [MQTT Discovery](mqtt-discovery.md).
