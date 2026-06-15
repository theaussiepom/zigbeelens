# MQTT Discovery

ZigbeeLens can optionally publish **summary Home Assistant entities** using [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery). This is a lightweight automation/status path for users who prefer MQTT over installing the HACS integration.

## Lens family MQTT conventions

Shared rules across [ZigbeeLens](https://github.com/theaussiepom/zigbeelens) and [ThreadLens](https://github.com/theaussiepom/threadlens). See [lens-family.md](lens-family.md).

| Rule | Detail |
|------|--------|
| **Global summary by default** | Overall health, incident state, device counts, collector status — one HA device |
| **Avoid per-device spam** | ZigbeeLens does not publish per-Zigbee-device entities by default |
| **Unknown vs zero** | Use `unknown` or omit when unobserved; use `0` only for observed zero counts |
| **Diagnostic naming** | Entity names describe status (“overall health”, “unavailable devices”), not control |
| **Availability** | Product liveness via availability topic (`online` / `offline`) |
| **No secrets** | Passwords, keys, and broker credentials never appear in discovery payloads |

ThreadLens equivalent: [mqtt-home-assistant.md](https://github.com/theaussiepom/threadlens/blob/main/docs/mqtt-home-assistant.md).

## What it does

- Publishes summary ZigbeeLens entities to Home Assistant via MQTT Discovery
- Exposes overall health, incident state, device counts, collector status, and per-network health
- Uses ZigbeeLens-owned topics only (`homeassistant/...` discovery configs and `zigbeelens/state/...` states)

## What it does not do

- Does **not** publish Zigbee2MQTT commands or request topics
- Does **not** mutate Zigbee state
- Does **not** expose every Zigbee device
- Does **not** replace the ZigbeeLens dashboard
- Does **not** replace the HACS integration repairs, diagnostics, config flow, or native companion panel

## HACS vs MQTT Discovery

| | HACS integration | MQTT Discovery |
|---|------------------|----------------|
| Install | HACS custom integration | Config flag only |
| Config flow | Yes | No |
| Repairs / diagnostics | Yes | No |
| Native companion panel | Yes | No |
| Summary entities | Yes | Yes |
| Best for | Native HA experience | Simple MQTT automations without HACS |

You generally do **not** need both enabled unless you explicitly want duplicate summary entities.

**Recommended:** use the [HACS integration](hacs.md) for native Home Assistant polish. Enable MQTT Discovery only when you want HA entities without HACS.

## Configuration

Both toggles must be enabled:

```yaml
features:
  mqtt_discovery: true

mqtt_discovery:
  enabled: true
  topic_prefix: homeassistant
  state_topic_prefix: zigbeelens
  retain: true
  device_name: ZigbeeLens
  object_id_prefix: zigbeelens
```

- `features.mqtt_discovery` — user-facing on/off switch (default **false** in add-on and Docker examples)
- `mqtt_discovery.*` — advanced topic and retain settings

## Entities

All entities group under one Home Assistant device: **ZigbeeLens**.

### Global summary

- Overall health (`ok` / `watch` / `incident` / `unknown`)
- Active incident (binary, problem device class)
- Incident state (`none` / `watch` / `incident`)
- Unavailable, recently unstable, router risks, stale, weak-link, low-battery, unknown device counts
- Network count, device count
- MQTT collector connected (binary, connectivity)
- Core running (binary, connectivity)

### Per network

For each configured network:

- `{Network} health`
- `{Network} unavailable devices`
- `{Network} router risks`

Network IDs are sanitized for MQTT object IDs. Keep `networks[].id` stable.

## Topics

Discovery configs:

```
homeassistant/sensor/zigbeelens_overall_health/config
homeassistant/binary_sensor/zigbeelens_active_incident/config
```

State payloads:

```
zigbeelens/state/overall
zigbeelens/state/incidents
zigbeelens/state/counts/unavailable_devices
zigbeelens/state/networks/{network_id}/health
zigbeelens/status
```

ZigbeeLens **never** publishes under your Zigbee2MQTT `base_topic`.

## Safety

- The MQTT collector client remains **subscribe-only**
- Discovery uses a separate publisher client with strict topic validation
- Rejected topics include `/bridge/request/`, `/set`, wildcards, and anything under configured Zigbee2MQTT base topics
- State payloads are summaries only — no raw reports, passwords, or full device lists

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Entities not appearing | `features.mqtt_discovery: true`, MQTT Discovery enabled in HA, broker reachable from Core |
| Wrong entity names | `object_id_prefix` and `topic_prefix` settings |
| Stale retained entities | Disable discovery and clear retained `homeassistant/.../zigbeelens_*` config topics |
| Duplicate entities | Disable either HACS integration entities or MQTT Discovery — both expose summaries |
| Cleanup after disable | Restart Core with discovery off; retained discovery configs may need manual broker cleanup |

## Status in the UI

**Settings → MQTT Discovery** shows enabled state, publisher connection, published entity count, last publish time, and last error (redacted).

See also [HACS integration](hacs.md) and [Docker deployment](docker.md).
