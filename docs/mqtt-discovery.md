# MQTT Discovery

ZigbeeLens can optionally publish **decision-contract-v2 summary Home Assistant entities** using [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery).

**Breaking change (Track 5):** the previous Lens-bucket summary entities (`health`, `issues`, `needs_attention`, `recently_unstable`, `diagnostics_limited`) are superseded. On start, ZigbeeLens publishes retained empty tombstones for those discovery config topics. The factual `unavailable` entity key is retained with identical semantics.

## Decision MQTT conventions

| Rule | Detail |
|------|--------|
| **Global summary by default** | Six summary sensors on one HA device |
| **No per-device spam** | No per-Zigbee-device entities by default |
| **Unknown vs zero** | `unknown` when not observable; `0` only for observed zero |
| **Decision vocabulary** | States use canonical `DecisionStatus` / counts — not Lens buckets |
| **Availability** | `zigbeelens/status` with `online` / `offline` |
| **No secrets** | Passwords, tokens, IEEE addresses, and names never appear in payloads |

## Decision summary entities (default)

All entities group under one Home Assistant device: **ZigbeeLens**.

| HA entity | Entity key | State topic | Purpose |
|-----------|------------|-------------|---------|
| ZigbeeLens Decision Status | `decision_status` | `zigbeelens/summary/decision_status/state` | Canonical `DecisionStatus` |
| ZigbeeLens Review First | `review_first` | `zigbeelens/summary/review_first/state` | Count of `review_first` subjects |
| ZigbeeLens Worth Reviewing | `worth_reviewing` | `zigbeelens/summary/worth_reviewing/state` | Count of `worth_reviewing` subjects |
| ZigbeeLens Coverage Warnings | `coverage_warnings` | `zigbeelens/summary/coverage_warnings/state` | Data coverage warning count |
| ZigbeeLens Active Incidents | `active_incidents` | `zigbeelens/summary/active_incidents/state` | Active incident count |
| ZigbeeLens Unavailable Devices | `unavailable` | `zigbeelens/summary/unavailable/state` | Factual unavailable device count |

Attributes publish to matching `.../attributes` topics and may include:

- `product`, `version`, `decision_contract_version`
- `overall_decision_status`, `highest_priority`
- `status_counts`, `priority_counts`
- `coverage_warning_count`, `active_incident_count`, `unavailable_device_count`
- `generated_at`, `collector_connected`, `observation_reliable`, `redaction_profile`

They do **not** include health primary, Lens buckets, device identifiers, names, tokens, or raw evidence.

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
| Live mode, MQTT collector disconnected | Decision status → `data_unavailable`; count entities → `unknown` |
| Mock mode or collector connected, observed zero | `0` |
| Observed count | integer string |

Never convert unobservable data to zero.

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

After deploying decision-contract MQTT:

1. ZigbeeLens automatically tombstones superseded Lens discovery configs on start:
   - `homeassistant/sensor/zigbeelens/health/config`
   - `homeassistant/sensor/zigbeelens/issues/config`
   - `homeassistant/sensor/zigbeelens/needs_attention/config`
   - `homeassistant/sensor/zigbeelens/recently_unstable/config`
   - `homeassistant/sensor/zigbeelens/diagnostics_limited/config`
2. Older pre-clean flat discovery topics remain listed in `LEGACY_DISCOVERY_TOPICS` for optional manual cleanup via `cleanup_legacy_discovery_configs()`.
3. In Home Assistant, remove any unavailable superseded entities from the entity registry if they remain after the tombstones.

ZigbeeLens never publishes under Zigbee2MQTT base topics or `/set`.
