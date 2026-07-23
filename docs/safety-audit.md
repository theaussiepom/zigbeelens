# Safety audit

This safety audit records the implemented ZigbeeLens boundaries and the checks
that protect them.

**Principle:** ZigbeeLens may collect evidence and issue narrowly allowlisted
diagnostic MQTT requests, but it does not control Zigbee devices or change
Zigbee network configuration.

## MQTT collector

The production collector client has no `publish()` method. For each configured
Zigbee2MQTT base topic it subscribes to:

```text
{base_topic}/bridge/state
{base_topic}/bridge/info
{base_topic}/bridge/devices
{base_topic}/bridge/event
{base_topic}/bridge/logging
{base_topic}/bridge/health
{base_topic}/+/availability
{base_topic}/+
```

When `topology.enabled` is true it also subscribes to the exact response topic:

```text
{base_topic}/bridge/response/networkmap
```

The collector itself is subscribe-only. It does not publish device `/set`,
permit-join, remove, reset, OTA, bind/unbind, or bridge request topics. The fake
collector client's `publish()` exists only so tests can assert it was not used.

Implementation: `apps/core/src/zigbeelens/mqtt/client.py`,
`mqtt/topics.py`, `mqtt/collector.py`
Tests: `apps/core/tests/test_mqtt_collector.py`,
`test_mqtt_topics.py`, `test_safety_guardrails.py`

## Topology diagnostic request

Topology uses a separate publisher from the collector. It can publish only:

```text
{base_topic}/bridge/request/networkmap
```

The base topic must match one configured network, wildcards and `/set` are
rejected, QoS is 0, retain is false, and the payload is:

```json
{"type":"raw","routes":true}
```

Topology is enabled by the source defaults. In live mode, the default startup
policy waits for collector connection, every configured bridge to be observed
online, and a 60-second stable delay, then requests one snapshot per network.
That system startup scan is configuration-authorized; it is not a per-click
manual confirmation.

Periodic capture is off by default (`refresh_interval_seconds: 0` and automatic
capture flags off). Manual capture is off by default and requires all of:

- `topology.enabled: true`
- `features.manual_network_map: true`
- `topology.manual_capture_enabled: true`
- a request body with exact boolean `confirmed: true`

The warning explains that a network-map request can temporarily add mesh load.
It does not claim that the diagnostic request is a device-control write.

Implementation: `apps/core/src/zigbeelens/topology/topics.py`,
`topology/publisher.py`, `topology/scheduler.py`, `topology/service.py`
Tests: `apps/core/tests/test_topology.py`, `test_topology_api.py`,
`test_topology_startup.py`

## MQTT Discovery

MQTT Discovery is effective only when both `features.mqtt_discovery` and
`mqtt_discovery.enabled` are true. The source defaults leave the feature flag
off.

When enabled, the separate Discovery publisher writes:

- retained Home Assistant discovery config records (and retained-empty
  tombstones) under the configured discovery prefix;
- ZigbeeLens summary state and attribute records under the configured state
  prefix;
- retained online/offline availability, including a broker last will.

Normal publish calls reject wildcards, `/set`, `/bridge/request/`, and every
configured Zigbee2MQTT base-topic subtree. The built-in allowed roots are
`homeassistant/` and `zigbeelens/`; the configured discovery prefix is also
allowed. Operators must keep both configured prefixes outside every
Zigbee2MQTT base topic.

Current release blocker: the MQTT client last will is registered at
`{state_topic_prefix}/status` before the normal topic validator runs. A
misconfigured state prefix can therefore overlap a Zigbee2MQTT base topic for
that last-will write. Keep the default state prefix and enforce broker ACLs
until registration validates the topic against configured network roots.

Implementation: `apps/core/src/zigbeelens/mqtt_discovery/topics.py`,
`mqtt_discovery/publisher.py`, `mqtt_discovery/service.py`
Tests: `apps/core/tests/test_mqtt_discovery.py`

## Reports

| Check | Status |
|-------|--------|
| Redaction runs before preview/storage/download | Enforced |
| Recognised passwords, tokens, network keys, and connection credentials are scrubbed | Enforced |
| Every new stored body is exact `ReportDetailV3` | Enforced |
| Saved list/detail/download fail closed for malformed or non-v3 bodies | Enforced |
| Migration 014 removes all development-era saved reports once at schema 13 → 14 | Enforced |

`standard` deliberately retains some non-secret local context, while
`public_safe` and `strict` remove more identifiers. See
[redaction.md](redaction.md); users must still review an export before sharing.

Implementation: `apps/core/src/zigbeelens/services/reports.py`,
`report_redaction.py`, `report_storage.py`
Tests: report/redaction tests and `apps/core/tests/contracts/test_report_v3_contract.py`

## HTTP authentication

| Boundary | Status |
|----------|--------|
| Protected reads and mutations accept configured bearer, valid browser session, trusted local, or validated HA ingress identity as applicable | Enforced |
| Browser-session mutations require an allowed exact Origin and CSRF token before body decoding | Enforced |
| Bearer and ingress mutations do not use Core session CSRF | Enforced |
| Home Assistant identity is accepted only from an exact configured ASGI peer | Enforced |
| Client-supplied remote-user headers are stripped | Enforced |
| API tokens, session IDs/cookies, CSRF secrets, and HA user IDs are not projected in status/report output | Enforced |

Creating/deleting reports, requesting topology capture, and replacing/clearing
Home Assistant enrichment change ZigbeeLens-local state. They do not control a
Zigbee device.

## Evidence semantics

- A topology snapshot is capture-time evidence, not a live map.
- A stored neighbour link is a relationship reported in that snapshot.
- A route hint requires route-table evidence (`route_count > 0`); it is not
  derived from LQI or neighbour adjacency.
- A recent missing/last-known link describes differences between usable stored
  snapshots. Absence does not prove a failure.
- Passive-derived investigation links are suggestions to review evidence
  together; they are not topology evidence.
- Unavailable or limited evidence remains unknown. It is not converted to a
  measured zero or a healthy conclusion.

The stored snapshot-level raw payload is scrubbed before persistence. Current
release blocker: parsed node/link `raw_json` is built from the unredacted
decoded response and retained locally. Public API/report projections omit that
field, but omission is not a reviewed local-storage scrub or retention
contract. Resolve that boundary before treating topology persistence as fully
redacted.

Human-facing terminology follows [ubiquitous-language.md](ubiquitous-language.md).

## UI and Home Assistant companion

| Check | Status |
|-------|--------|
| No repair/reset/remove/permit-join device controls | Enforced |
| Manual topology capture shows a warning and requires confirmation | Enforced |
| Incident and Decision copy carries evidence/limitations rather than causal claims | Enforced |
| Contextual report dialog shows scope, redaction profile, and preview before save | Enforced |
| Home Assistant integration reads Core; it does not publish Zigbee device-control commands | Enforced |
| Home Assistant diagnostics redact secrets | Enforced |
| No Home Assistant control services/entities are introduced | Enforced |

Release safety ownership is split across the two production UI sources:

- Core UI production `.ts` and `.tsx` under `apps/ui/src`;
- Home Assistant companion panel production JavaScript under
  `apps/ha_integration/custom_components/zigbeelens/panel`, including the
  canonical `zigbeelens-panel.js` entrypoint.

`apps/core/tests/test_safety_guardrails.py` applies the same Zigbee
mutation-control phrase policy to both corpora, with separate missing-source,
empty-corpus, and unsafe-control diagnostics. The fail-closed
`scripts/validate-safety-guardrails.sh` wrapper is the release owner: it rejects
zero collected tests and any skip, failure, or error.

Core topology's allowlisted network-map request and optional MQTT Discovery
publishes are Core policies, not actions performed by the Home Assistant
integration.

## Verification commands

From `apps/core`:

```bash
uv run pytest -q \
  tests/test_safety_guardrails.py \
  tests/test_mqtt_topics.py \
  tests/test_mqtt_discovery.py \
  tests/test_topology.py \
  tests/test_topology_api.py \
  tests/test_topology_startup.py

uv run pytest -q \
  tests/test_api_auth.py \
  tests/test_browser_sessions.py \
  tests/test_ha_ingress.py \
  tests/contracts/test_report_v3_contract.py \
  tests/contracts/test_migration_014_report_reset.py
```

From the repository root, run contract validation:

```bash
bash scripts/validate-safety-guardrails.sh
bash scripts/validate-contracts.sh
```

## Non-goals

ZigbeeLens does not implement:

- permit join;
- device remove/reset/configure;
- bind/unbind;
- OTA firmware updates;
- channel changes;
- periodic topology refresh by default;
- Zigbee2MQTT replacement;
- cloud sync.

## Related

- [architecture.md](architecture.md)
- [topology.md](topology.md)
- [mqtt-discovery.md](mqtt-discovery.md)
- [security.md](security.md)
- [release.md](release.md)
