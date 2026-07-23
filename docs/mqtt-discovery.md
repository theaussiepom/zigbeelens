# MQTT Discovery

ZigbeeLens can optionally publish decision-contract-v2 summary entities for
Home Assistant MQTT Discovery. This is a separate output publisher, not part of
the subscribe-only Zigbee2MQTT collector.

The previous Lens-bucket entities (`health`, `issues`, `needs_attention`,
`recently_unstable`, and `diagnostics_limited`) are superseded. When Discovery
starts, Core publishes retained-empty tombstones for those config topics under
the active discovery prefix. The factual `unavailable` entity remains.

## Decision summary entities

The default configuration creates six summary sensors on one Home Assistant
device. It does not create one entity per Zigbee device.

| Home Assistant entity | Entity key | Default state topic | Meaning |
|-----------------------|------------|---------------------|---------|
| ZigbeeLens Decision Status | `decision_status` | `zigbeelens/summary/decision_status/state` | Canonical overall `DecisionStatus` |
| ZigbeeLens Review First | `review_first` | `zigbeelens/summary/review_first/state` | Count of `review_first` subjects |
| ZigbeeLens Worth Reviewing | `worth_reviewing` | `zigbeelens/summary/worth_reviewing/state` | Count of `worth_reviewing` subjects |
| ZigbeeLens Coverage Warnings | `coverage_warnings` | `zigbeelens/summary/coverage_warnings/state` | Data coverage warning count |
| ZigbeeLens Active Incidents | `active_incidents` | `zigbeelens/summary/active_incidents/state` | Active incident count |
| ZigbeeLens Unavailable Devices | `unavailable` | `zigbeelens/summary/unavailable/state` | Factual unavailable-device count |

Attributes publish to matching `.../attributes` topics. They may include:

- `product`, `version`, and `decision_contract_version`;
- overall decision status and highest priority;
- status/priority counts;
- coverage-warning, active-incident, and unavailable-device counts;
- generation time, collector connection, observation reliability, and the
  public-safe presentation profile.

They do not include per-device IEEE addresses or friendly names, credentials,
tokens, or raw evidence.

## Unknown versus zero

| Situation | Published state |
|-----------|-----------------|
| Live mode and collector disconnected | Decision status `data_unavailable`; count states `unknown` |
| Observation is reliable and the measured count is zero | `0` |
| Observation is reliable and the count is non-zero | Integer string |

Unavailable data is never converted to zero.

## Effective enablement

Both toggles must be true:

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

The source defaults are `features.mqtt_discovery: false` and
`mqtt_discovery.enabled: true`, so Discovery is effectively off until the
feature flag is enabled. Restart Core after changing these settings. The
current decision-summary entity IDs retain the fixed `zigbeelens_` object-ID
prefix; `mqtt_discovery.object_id_prefix` is accepted by configuration but does
not currently change them.

## Publish contract

With default prefixes, Core writes:

| Kind | Pattern |
|------|---------|
| Discovery configs/tombstones | `homeassistant/<component>/zigbeelens/<entity_key>/config` |
| State | `zigbeelens/summary/<entity_key>/state` |
| Attributes | `zigbeelens/summary/<entity_key>/attributes` |
| Availability and broker last will | `zigbeelens/status` |

Discovery configs and tombstones are retained. State, attributes, and
online/offline availability follow `mqtt_discovery.retain`; the broker last
will is retained.

Normal Discovery publish calls validate topics before sending. They reject:

- `+` or `#` wildcards;
- a `/set` suffix;
- `/bridge/request/`;
- a configured Zigbee2MQTT base topic or anything below it;
- a root outside `homeassistant/`, `zigbeelens/`, or the configured discovery
  prefix.

`topic_prefix` adds its normalized root to that allowlist.
`state_topic_prefix` does not add another allowed root, so a custom state prefix
must be below `homeassistant/`, `zigbeelens/`, or the configured discovery
prefix. Keep both prefixes outside every Zigbee2MQTT base topic. Core registers
the broker last will at `{state_topic_prefix}/status` before the normal publish
validator runs. Configuration loading does not currently reject a state prefix
that overlaps a Zigbee2MQTT base topic. Keep the default `zigbeelens` state
prefix (or independently verify a custom one), and use broker ACLs to restrict
that intentional ZigbeeLens-owned write until the last-will path is validated
before registration.

MQTT Discovery never needs a Zigbee2MQTT device `/set` permission. Topology's
separately allowlisted network-map request is documented in
[topology.md](topology.md).

## Migration and cleanup

On every enabled startup, ZigbeeLens tombstones the five superseded nested Lens
config topics under the currently configured discovery prefix. Home Assistant
may retain disabled entity-registry entries after their MQTT config is removed;
delete those entries manually if desired.

Older pre-clean flat topics remain in Core's developer-only
`LEGACY_DISCOVERY_TOPICS` list. There is no public cleanup API for that list;
broker administrators can remove those retained records manually if they were
created by an older development build.

## Troubleshooting

If entities do not appear:

1. Confirm both enablement flags are true.
2. Confirm Home Assistant and Core use the same broker.
3. Check `GET /api/v1/health` for Discovery status.
4. Verify ACLs allow the configured config/state/availability topics.
5. Verify neither configured prefix overlaps a Zigbee2MQTT base topic.
6. Look for a safe `Discovery publisher failed` error in Core logs.

See [troubleshooting.md](troubleshooting.md) and
[safety-audit.md](safety-audit.md).
