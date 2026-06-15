# MQTT Discovery

ZigbeeLens can optionally publish **Lens-family summary Home Assistant entities** using [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery).

**Backward compatibility:** Phase 3C intentionally replaces the previous MQTT entity model. After deploying, delete stale retained discovery configs and remove old HA entities (see [Migration](#migration)).

## Lens family MQTT conventions

Shared rules across [ZigbeeLens](https://github.com/theaussiepom/zigbeelens) and [ThreadLens](https://github.com/theaussiepom/threadlens). See [lens-family.md](lens-family.md).

| Rule | Detail |
|------|--------|
| **Global summary by default** | Six summary sensors on one HA device |
| **No per-device spam** | No per-Zigbee-device entities by default |
| **Unknown vs zero** | `unknown` when not observable; `0` only for observed zero |
| **Diagnostic naming** | Names describe status, not control |
| **Availability** | `zigbeelens/status` with `online` / `offline` |
| **No secrets** | Passwords and keys never appear in discovery payloads |

ThreadLens equivalent: [mqtt-home-assistant.md](https://github.com/theaussiepom/threadlens/blob/main/docs/mqtt-home-assistant.md).

## Clean summary entities (default)

All entities group under one Home Assistant device: **ZigbeeLens**.

| HA entity | State topic | Purpose |
|-----------|-------------|---------|
| ZigbeeLens Health | `zigbeelens/summary/health/state` | Overall Lens bucket |
| ZigbeeLens Issues | `zigbeelens/summary/issues/state` | Total issue count |
| ZigbeeLens Unavailable Devices | `zigbeelens/summary/unavailable/state` | Unavailable device count |
| ZigbeeLens Needs Attention | `zigbeelens/summary/needs_attention/state` | Needs attention count |
| ZigbeeLens Recently Unstable | `zigbeelens/summary/recently_unstable/state` | Recently unstable count |
| ZigbeeLens Diagnostics Limited | `zigbeelens/summary/diagnostics_limited/state` | Diagnostics limited count |

Attributes publish to matching `.../attributes` topics and include:

- `product`, `version`, `lens_bucket`, `lens_bucket_label`
- `issue_count`, bucket counts, `generated_at`, `redaction_profile`

## Topic patterns

| Kind | Pattern |
|------|---------|
| Discovery config | `homeassistant/sensor/zigbeelens/<entity_key>/config` |
| State | `zigbeelens/summary/<entity_key>/state` |
| Attributes | `zigbeelens/summary/<entity_key>/attributes` |
| Availability | `zigbeelens/status` |

## Unknown vs zero

| Situation | MQTT state |
|-----------|------------|
| Live mode, MQTT collector disconnected | Count entities → `unknown` |
| Mock mode or collector connected, observed zero | `0` |
| Observed count | integer string |

Health entity state uses Lens bucket strings (`healthy`, `recently_unstable`, `needs_attention`, etc.).

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
```

## Migration

After deploying the clean Lens MQTT model:

1. Stop ZigbeeLens (publishes `offline` on `zigbeelens/status`).
2. Clear stale retained discovery configs for old entities, for example:

```bash
mosquitto_pub -h broker.mqtt -t 'homeassistant/sensor/zigbeelens_overall_health/config' -r -n
mosquitto_pub -h broker.mqtt -t 'homeassistant/binary_sensor/zigbeelens_active_incident/config' -r -n
# repeat for other old zigbeelens_* discovery topics
```

Or call `cleanup_legacy_discovery_configs()` from the discovery service when connected.

3. In Home Assistant: **Settings → Devices & services → MQTT → Entities** — delete stale ZigbeeLens entities.
4. Restart ZigbeeLens and reload the MQTT integration if needed.

Old discovery topics are listed in `zigbeelens.mqtt_discovery.topics.LEGACY_DISCOVERY_TOPICS`.

## What it does not do

- Does **not** publish Zigbee2MQTT commands or request topics
- Does **not** mutate Zigbee state
- Does **not** expose every Zigbee device
- Does **not** replace the HACS integration or dashboard

## HACS vs MQTT Discovery

Use the [HACS integration](hacs.md) for native Home Assistant polish. Enable MQTT Discovery only when you want summary entities without HACS.

## Safety

The collector remains subscribe-only. The discovery publisher validates topics and rejects Zigbee2MQTT base topics, wildcards, and `/set` paths.
