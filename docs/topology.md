# Topology snapshots

ZigbeeLens can capture **point-in-time Zigbee2MQTT network map snapshots** to enrich router risk and incident context. Topology is never required for core diagnostics to work.

## What topology snapshots do

- Ask Zigbee2MQTT for a network map via the single allowed request topic: `{base_topic}/bridge/request/networkmap`
- Store a redacted snapshot with nodes, links, and counts
- Enrich router risk and correlated incident evidence
- Show snapshot status in Advanced Topology snapshots support and Settings

## Product surfaces

Primary comparison workflow:

1. Devices → Device Detail
2. Device Story
3. Snapshot history (compare an earlier usable snapshot with the latest usable snapshot)

Mesh NodeDrawer remains a compact inspector and links to full Device Detail
instead of duplicating snapshot-history comparison.

Advanced & support:

- `/topology` — landing for capture status and per-network raw snapshot entry
- `/topology/:networkId` — exact point-in-time raw detail (collapsed node/link contents)

Whole-network `GET /api/topology/{network_id}/snapshots/compare` remains an
API/debug capability, not a current product workflow.

## Default behaviour

Topology is **enabled by default**.

After ZigbeeLens startup:

1. Wait until the MQTT collector is connected
2. Confirm each configured Zigbee2MQTT bridge is observed **online**
3. Wait a short grace period so startup retained MQTT messages settle
4. Request **one** topology snapshot per network

After that startup snapshot, ZigbeeLens relies on **passive MQTT updates** (devices, availability, linkquality, bridge state) by default. Periodic active topology scans are **disabled** unless explicitly configured.

## Why startup is delayed

Network map requests can temporarily make a Zigbee network less responsive, especially on larger networks. ZigbeeLens therefore:

- Does **not** request topology immediately at container start
- Does **not** request topology before the MQTT collector is connected
- Does **not** request topology before the Zigbee2MQTT bridge is observed online
- Waits `startup_stable_delay_seconds` after collector + bridge readiness before the startup scan

Manual capture still requires explicit user confirmation.

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

```yaml
topology:
  enabled: true
  startup_scan: true
  startup_stable_delay_seconds: 60
  refresh_interval_seconds: 0
  manual_capture_enabled: false
  automatic_capture_enabled: false
  capture_on_incident: false
  max_snapshots_per_network: 30
  warn_before_capture: true
```

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | `true` | Subscribe to topology responses and allow snapshot storage |
| `startup_scan` | `true` | One active network map request per network after startup stability |
| `startup_stable_delay_seconds` | `60` | Grace period after collector + bridge readiness before startup scan |
| `refresh_interval_seconds` | `0` | Periodic active scans; `0` disables periodic polling |
| `manual_capture_enabled` | `false` | UI/API manual capture (also needs `features.manual_network_map: true`) |

Legacy periodic scheduling remains available via `automatic_capture_enabled` + `automatic_capture_interval_hours` when `refresh_interval_seconds` is `0`.

To disable topology entirely:

```yaml
topology:
  enabled: false
  startup_scan: false
```

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
