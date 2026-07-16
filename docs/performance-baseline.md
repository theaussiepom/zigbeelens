# Track 3D bulk composition reads performance baseline

Base commit for Track 3A history: `09f10a8` (final merged Track 2 base). Track 3A instrumentation landed via `perf/query-baseline-instrumentation`. Track 3B atomic MQTT ingestion landed via `perf/atomic-mqtt-ingestion`. Track 3C incremental device evaluation landed via `perf/incremental-device-evaluation` (merge `98ab5c8`). This document records **Track 3D current totals** after batching incident/device/HA composition reads and scoping Device/Incident detail events in SQL, and preserves **Track 3A / Track 3B / Track 3C history** for comparison.

These are planning snapshots, not accepted performance budgets.

## Base behaviour evidence

Track 1 and Track 2 behaviour was confirmed before Track 3A changes: Device Story exposes `related_unresolved_incident_ids`, incident membership is separate from current-issue relevance, canonical coverage evidence is used, and EvaluationCoordinator owns coherent health → incident → dashboard sequencing.

Track 3B preserved those semantics with one `BEGIN IMMEDIATE` ingestion transaction. Track 3C preserved them with incremental target-device evaluation after commit. Track 3D preserves them again: read composition uses request-local immutable contexts only; Device Story related incident IDs remain contextual; write-path authority and incremental evaluation are unchanged. Health evaluation runs before Devices builds incident-sensitive context, and Dashboard reuses one ActiveIncidentReadContext.

## Consistency rule

> Device events update their target immediately. Time-only changes for unrelated devices are reconciled by the bounded periodic full-estate evaluation.

The existing 300-second periodic full-estate evaluation remains the correctness backstop. Track 3D does not add caches, debounce timers, or shared mutable request state.

## Measurement method

Measurements use pytest temporary SQLite databases only. The active ZigbeeLens database is not read, copied, migrated, reset, or deleted. Each operation is measured against a fresh deterministic fixture, warmed intentionally with `EvaluationCoordinator`, wrapped in a frozen request-time clock at `2026-07-15T12:00:00+00:00`, reset to zero query counters, and then executed exactly once. Classification records the primary statement/table category selected from the normalized SQL shape; it does not attempt to count every joined table as a separate category. Top repeated statements are normalized and contain no bound values.

Physical transaction counting rules:

- `execute_count` excludes the raw `BEGIN IMMEDIATE` statement;
- physical commits and rollbacks are counted separately via observers;
- deferred repository `commit()` requests inside an open transaction are not physical commits;
- transaction-control SQL is classified as `transaction.control` and must not appear under `other`.

## Deterministic fixtures

| Fixture | Estate | Contents |
|---|---:|---|
| Compact | 1 network / 20 devices | One Home inventory refresh containing the existing 20 Home IEEE addresses; target device is `devices["home"][5]`, an EndDevice intentionally absent from latest Home topology nodes/links but present historically; mixed coordinator/router/end-device roles, mains/battery devices, online/offline/stale/low-battery facts, sparse and dense snapshot histories for rhythm/LQI/battery, 10 parsed topology snapshots with nodes and links, historical missing link evidence, route hints, HA enrichment subset, open/watching/resolved incidents, incident-device references, lifecycle events, and filter-after-limit reproduction events. |
| Beast | 2 networks / 164 devices | One Home inventory refresh with the existing 120 Home IEEE addresses plus one Office inventory refresh with the existing 44 Office IEEE addresses; the same deterministic fixture features as Compact, plus more than 150 global events and multi-network incident history. |

## Statement categories

`read.*` and `write.*` categories cover networks, devices, device current state, device snapshots, availability changes, metric samples, health snapshots, incidents, incident devices, events, topology snapshots/nodes/links, HA enrichment, reports, schema checks, bridge snapshots, collector status, unresolved messages, commits, rollbacks, and `other` for unknown shapes.

## Track 3A → Track 3B commit comparison

Historical Track 3A totals counted every repository `commit()` call, including deferred writes that are no longer physical commits under Track 3B. Track 3B totals count physical commits only. Ingestion commits are the physical commits owned by the MQTT ingestion transaction(s); remaining commits are post-commit evaluation / incident persistence.

| Operation | Track 3A commits | Track 3B total commits | Ingestion commits | Delta |
|---|---:|---:|---:|---:|
| Payload | 8 | 3 | 1 | -5 |
| Availability | 11 | 8 | 1 | -3 |
| Compact inventory | 50 | 9 | 1 | -41 |
| Beast inventory | 357 | 27 | 2 | -330 |

Beast inventory performs two MQTT ingestion transactions (Home then Office), so ingestion commits are 2.

## Track 3B → Track 3C execute comparison

Track 3C keeps Track 3B ingestion-transaction commit counts unchanged for payload and availability. Post-commit cost drops because device-scoped events reclassify only the target device and recompute network/bridge aggregates from the cached estate snapshot.

| Operation | Track 3B total | Track 3C total | Track 3B post-commit | Track 3C post-commit | Delta |
|---|---:|---:|---:|---:|---:|
| Compact payload | 90 | 36 | 83 | 29 | -54 |
| Compact availability | 100 | 46 | 94 | 40 | -54 |
| Beast payload | — | 62 | — | 55 | — |
| Beast availability | — | 75 | — | 69 | — |
| Compact inventory | 136 | 136 | 93 | 93 | 0 |
| Beast inventory | 963 | 963 | 629 | 629 | 0 |

Beast payload/availability target-event baselines are new in Track 3C. Compact and Beast inventory paths still call full-network evaluation and therefore keep Track 3B totals.

## Track 3C → Track 3D execute comparison

Track 3D replaces per-device/per-incident N+1 composition reads with bounded bulk repository APIs and scoped event queries. Ingestion and incremental evaluation baselines are unchanged.

| Operation | Track 3C executes | Track 3D executes | Delta | Main removed category |
|---|---:|---:|---:|---|
| Dashboard Compact | 328 | 109 | -219 | read.incident_devices N+1 |
| Dashboard Beast | 3467 | 282 | -3185 | read.incident_devices N+1 |
| Devices Compact | 355 | 83 | -272 | read.incident_devices N+1 |
| Devices Beast | 4169 | 406 | -3763 | read.incident_devices N+1 |
| Incident list | 97 | 51 | -46 | per-incident device/event loads |
| Incident detail | 62 | 47 | -15 | global list_events filter-after-limit |
| Device detail | 57 | 54 | -3 | network list_events filter-after-limit |
| Full report preview | 798 | 262 | -536 | read.incident_devices N+1 |
| Network report preview | 798 | 262 | -536 | read.incident_devices N+1 |
| Incident report preview | 639 | 317 | -322 | read.incident_devices N+1 |
| Device report preview | 510 | 237 | -273 | read.incident_devices N+1 |
| EvidenceGraphService.build | 99 | 99 | 0 | unchanged (no topology rewrite) |

## Track 3C ingestion vs post-commit phases

Counters are captured at health-callback entry. At that point the ingestion transaction has already physically committed. Post-commit work is EvaluationCoordinator / incident persistence and any trailing assertion reads included in the measured operation. Track 3D does not change these measurements.

| Operation | Ingestion executes | Ingestion commits | Post-commit executes | Post-commit commits | Total executes | Total commits |
|---|---:|---:|---:|---:|---:|---:|
| Compact payload | 7 | 1 | 29 | 2 | 36 | 3 |
| Beast payload | 7 | 1 | 55 | 2 | 62 | 3 |
| Compact availability | 6 | 1 | 40 | 7 | 46 | 8 |
| Beast availability | 6 | 1 | 69 | 7 | 75 | 8 |
| Compact inventory | 43 | 1 | 93 | 8 | 136 | 9 |
| Beast inventory | 334 | 2 | 629 | 25 | 963 | 27 |

## Track 3D total baseline table

| Operation | Fixture | State | Executes | Executemany | Commits | Rollbacks | Other | Top repeated category |
|---|---|---|---:|---:|---:|---:|---:|---|
| Availability change ingestion | compact | warm | 46 | 0 | 8 | 0 | 0 | transaction.commit (8) |
| Availability change ingestion | beast | warm | 75 | 0 | 8 | 0 | 0 | read.incidents (10) |
| Dashboard composition | compact | warm | 109 | 0 | 0 | 0 | 0 | read.schema (30) |
| Dashboard composition | beast | warm | 282 | 0 | 0 | 0 | 0 | read.schema (87) |
| Device detail | compact | warm | 54 | 0 | 0 | 0 | 0 | read.topology_nodes (12) |
| Devices inventory composition | compact | warm | 83 | 0 | 0 | 0 | 0 | read.availability_changes (22) |
| Devices inventory composition | beast | warm | 406 | 0 | 0 | 0 | 0 | read.availability_changes (168) |
| EvidenceGraphService.build | compact | warm | 99 | 0 | 0 | 0 | 0 | read.schema (27) |
| Incident detail | compact | warm | 47 | 0 | 0 | 0 | 0 | read.topology_nodes (12) |
| Incident list | compact | warm | 51 | 0 | 0 | 0 | 0 | read.topology_nodes (12) |
| Device inventory refresh | beast | warm | 963 | 0 | 27 | 0 | 0 | read.availability_changes (168) |
| Device inventory refresh | compact | warm | 136 | 0 | 9 | 0 | 0 | read.health_snapshots (22) |
| Ordinary MQTT payload ingestion | compact | warm | 36 | 0 | 3 | 0 | 0 | read.schema (4) |
| Ordinary MQTT payload ingestion | beast | warm | 62 | 0 | 3 | 0 | 0 | read.incidents (10) |
| Device report preview | compact | warm | 237 | 0 | 0 | 0 | 0 | read.schema (43) |
| Full report preview | compact | warm | 262 | 0 | 0 | 0 | 0 | read.schema (42) |
| Incident report preview | compact | warm | 317 | 0 | 0 | 0 | 0 | read.schema (50) |
| Network report preview | compact | warm | 262 | 0 | 0 | 0 | 0 | read.schema (42) |

## Top repeated normalized statement shapes

### availability_ingestion

- 5× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `INSERT INTO events ( id, network_id, ieee_address, event_type, severity, title, summary, incident_id, payload_json, occurred_at ) VALUES (?)`
- 3× `SELECT source_ieee FROM topology_links WHERE snapshot_id = ? AND target_ieee = ? LIMIT ?`
- 3× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 3× `INSERT INTO incident_devices (incident_id, network_id, ieee_address, role) VALUES (?)`

### availability_ingestion_beast

- 9× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ? ORDER BY network_id, ieee_address, role`
- 9× `SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE dedup_key = ? AND lifecycle_state IN (?) ORDER BY updated_at DESC LIMIT ?`
- 9× `INSERT INTO incident_devices (incident_id, network_id, ieee_address, role) VALUES (?)`
- 7× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?`

### dashboard

- 30× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 23× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 17× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 8× `SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id = ? ORDER BY d.friendly_name`
- 6× `SELECT ieee_address, from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND changed_at >= ? ORDER BY changed_at ASC`

### dashboard_beast

- 87× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 72× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 34× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 26× `SELECT ieee_address, from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND changed_at >= ? ORDER BY changed_at ASC`
- 16× `SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id = ? ORDER BY d.friendly_name`

### device_detail

- 12× `SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address`
- 10× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 6× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?`
- 2× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`

### devices

- 20× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 20× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 12× `SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address`
- 10× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 5× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`

### devices_beast

- 164× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 164× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 24× `SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address`
- 20× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 9× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`

### evidence_graph

- 27× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 26× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 23× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 6× `SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id = ? ORDER BY d.friendly_name`
- 5× `SELECT ieee_address, from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND changed_at >= ? ORDER BY changed_at ASC`

### incident_detail

- 12× `SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address`
- 10× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 5× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?`
- 3× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`

### incident_list

- 12× `SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address`
- 10× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 5× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 5× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 5× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`

### inventory_ingestion_beast

- 164× `INSERT INTO devices ( network_id, ieee_address, friendly_name, device_type, power_source, manufacturer, model, interview_state, created_at, updated_at ) VALUES (?) ON CONFLICT(network_id, ieee_address) DO UPDATE SET friendly_name = excluded.friendly_name, device_type = excluded.device_type, power_source = excluded.power_source, manufacturer = COALESCE(excluded.manufacturer, devices.manufacturer), model = COALESCE(excluded.model, devices.model), interview_state = excluded.interview_state, updated_at = excluded.updated_at`
- 164× `INSERT OR IGNORE INTO device_current_state (network_id, ieee_address) VALUES (?)`
- 164× `SELECT COUNT(*) FROM availability_changes WHERE network_id = ? AND ieee_address = ? AND changed_at >= ?`
- 164× `SELECT primary_health, severity, confidence, summary, flags_json, evidence_json, counter_evidence_json, limitations_json, captured_at FROM health_snapshots WHERE scope = ? AND network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 53× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`

### inventory_ingestion_compact

- 20× `INSERT INTO devices ( network_id, ieee_address, friendly_name, device_type, power_source, manufacturer, model, interview_state, created_at, updated_at ) VALUES (?) ON CONFLICT(network_id, ieee_address) DO UPDATE SET friendly_name = excluded.friendly_name, device_type = excluded.device_type, power_source = excluded.power_source, manufacturer = COALESCE(excluded.manufacturer, devices.manufacturer), model = COALESCE(excluded.model, devices.model), interview_state = excluded.interview_state, updated_at = excluded.updated_at`
- 20× `INSERT OR IGNORE INTO device_current_state (network_id, ieee_address) VALUES (?)`
- 20× `SELECT COUNT(*) FROM availability_changes WHERE network_id = ? AND ieee_address = ? AND changed_at >= ?`
- 20× `SELECT primary_health, severity, confidence, summary, flags_json, evidence_json, counter_evidence_json, limitations_json, captured_at FROM health_snapshots WHERE scope = ? AND network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 8× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`

### payload_ingestion

- 4× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 2× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ? ORDER BY network_id, ieee_address, role`
- 2× `INSERT INTO metric_samples (network_id, ieee_address, metric_name, metric_value, sampled_at) VALUES (?)`
- 2× `INSERT INTO events ( id, network_id, ieee_address, event_type, severity, title, summary, incident_id, payload_json, occurred_at ) VALUES (?)`
- 2× `SELECT primary_health, severity, confidence, summary, flags_json, evidence_json, counter_evidence_json, limitations_json, captured_at FROM health_snapshots WHERE scope = ? AND network_id = ? AND ieee_address IS NULL ORDER BY captured_at DESC LIMIT ?`

### payload_ingestion_beast

- 9× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ? ORDER BY network_id, ieee_address, role`
- 9× `SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE dedup_key = ? AND lifecycle_state IN (?) ORDER BY updated_at DESC LIMIT ?`
- 7× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?`
- 3× `SELECT friendly_name FROM topology_nodes WHERE snapshot_id = ? AND ieee_address = ?`

### report_device

- 43× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 37× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 28× `SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address`
- 24× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 11× `SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?`

### report_full

- 42× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 37× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 28× `SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address`
- 25× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 25× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`

### report_incident

- 50× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 47× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 40× `SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address`
- 26× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 14× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`

### report_network

- 42× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 37× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 28× `SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address`
- 25× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 25× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`

## Filter-after-limit reproduction

The Beast fixture seeds more than 20 newer unrelated Home network events plus `older-target-device-event`, and more than 100 newer unrelated global events plus `older-target-incident-event`. Network/global `list_events` limits still exclude those older target rows. Track 3D Device Detail and Incident Detail use `list_events_for_device` / `list_events_for_incident` so the scoped target events are returned.

## Limitations and next scope

Exact values are snapshots for planning only, not budgets. Track 3D removes the principal Dashboard/Devices/Incident N+1 membership and per-device network/HA composition reads, and fixes scoped detail event correctness. Remaining Dashboard HA enrichment reads come from investigation/coverage composers (allowed to remain separate). Cross-surface Dashboard/report result sharing remains Track 3E.
