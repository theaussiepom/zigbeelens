# Safety audit

ZigbeeLens v0.1.0 safety audit. This document records intentional boundaries and verification points for release.

**Principle:** ZigbeeLens observes and explains — it does not mutate Zigbee networks.

## MQTT collector

| Check | Status |
|-------|--------|
| Subscribe-only to Zigbee2MQTT topics | Enforced |
| No publish to `{base_topic}/set` | Enforced |
| No publish to `{base_topic}/bridge/request/*` | Enforced |
| No wildcards published | N/A — collector does not publish |

Implementation: `apps/core/src/zigbeelens/mqtt/collector.py`  
Tests: `apps/core/tests/test_safety_guardrails.py`

The test MQTT client's `publish()` method exists only for test assertions — production collector paths do not call it.

## MQTT Discovery (optional, off by default)

| Check | Status |
|-------|--------|
| Disabled unless `features.mqtt_discovery` AND `mqtt_discovery.enabled` | Enforced |
| Publish only `homeassistant/...` and `zigbeelens/...` | Enforced |
| Reject `/bridge/request/` | Enforced |
| Reject `/set` suffix | Enforced |
| Reject configured Zigbee2MQTT base topics | Enforced |
| Reject wildcards | Enforced |

Implementation: `apps/core/src/zigbeelens/mqtt_discovery/topics.py`  
Tests: `apps/core/tests/test_mqtt_discovery.py`

## Topology (enabled by default)

| Check | Status |
|-------|--------|
| Enabled by default with startup scan only | Enforced |
| Startup scan waits for collector + bridge readiness | Enforced |
| No periodic active scan when `refresh_interval_seconds: 0` | Enforced |
| Manual capture requires explicit `confirmed: true` | Enforced |
| Single allowlisted topic: `{base_topic}/bridge/request/networkmap` | Enforced |
| No permit join, remove, reset, OTA topics | Enforced |

Implementation: `apps/core/src/zigbeelens/topology/topics.py`, `topology/publisher.py`  
Tests: `apps/core/tests/test_topology.py`

## Reports

| Check | Status |
|-------|--------|
| Redacted before storage | Enforced |
| Redacted before download | Enforced |
| Network keys/passwords/tokens absent from stored reports | Enforced |

Implementation: `apps/core/src/zigbeelens/services/reports.py`, `report_redaction.py`  
Tests: report and redaction tests in `apps/core/tests/`

## UI

| Check | Status |
|-------|--------|
| No repair/reset/remove/permit-join controls | Verified |
| Topology capture requires warning modal + confirmation | Enforced |
| Incident language uses evidence/limitations | Enforced |
| Reports page explains redaction profiles | Enforced |
| Contextual report dialog shows redaction profile and summary before save | Enforced |
| Reports mount fetches saved list only (no target discovery / preview) | Enforced |
| Save-and-download creates one stored report then downloads that ID | Enforced |
| Saved report list/detail/download accepts exact `ReportDetailV3` only | Enforced |

## HACS integration

| Check | Status |
|-------|--------|
| Read-only HTTP to Core | Enforced |
| No Zigbee mutation from HACS | Enforced |
| Diagnostics redacted | Enforced |
| Exact decision contract v1 negotiation | Enforced |
| Soft fallback when contract/payload unsupported | Enforced |
| No Decision entities or control services | Enforced |
| No HACS-side Decision wording / diagnosis | Enforced |

Implementation: `apps/ha_integration/custom_components/zigbeelens/`  
Tests: `apps/ha_integration/tests/`

Core topology may publish only the allowlisted Zigbee2MQTT network-map request for observation. That is Core topology policy, not an HACS action.

## Diagnostic language

| Check | Status |
|-------|--------|
| No definitive root-cause claims | Design requirement |
| Evidence + confidence + limitations on incidents | Enforced |
| Topology enrichment uses "suggests/consistent with" | Enforced |

## Verification commands

```bash
# Full guardrail suite
PYTHONPATH=apps/core/src pytest apps/core/tests/test_safety_guardrails.py -q

# Topic safety
PYTHONPATH=apps/core/src pytest apps/core/tests/test_mqtt_discovery.py apps/core/tests/test_topology.py -q
```

## Non-goals (explicit)

ZigbeeLens will not add in v0.1.x without explicit scope change:

- Permit join
- Device remove/reset/configure
- Bind/unbind
- OTA firmware updates
- Channel changes
- Automatic topology by default
- Zigbee2MQTT replacement
- Cloud sync

## Related

- [architecture.md](architecture.md)
- [security.md](security.md)
- [release.md](release.md)
