# Track 3C incremental device evaluation performance baseline

Base commit for Track 3A history: `09f10a8` (final merged Track 2 base). Track 3A instrumentation landed via `perf/query-baseline-instrumentation`. Track 3B atomic MQTT ingestion landed via `perf/atomic-mqtt-ingestion`. This document records **Track 3C current totals** after routing device-scoped MQTT events through incremental per-device health evaluation, and preserves **Track 3A / Track 3B history** for comparison.

These are planning snapshots, not accepted performance budgets.

## Base behaviour evidence

Track 1 and Track 2 behaviour was confirmed before Track 3A changes: Device Story exposes `related_unresolved_incident_ids`, incident membership is separate from current-issue relevance, canonical coverage evidence is used, and EvaluationCoordinator owns coherent health → incident → dashboard sequencing.

Track 3B preserved those semantics with one `BEGIN IMMEDIATE` ingestion transaction. Track 3C preserves them again: health and Dashboard callbacks still run only after the ingestion transaction physically commits; incident correlation still consumes a complete estate snapshot universe; Device Story and Mesh current-issue relevance remain independently current facts.

## Consistency rule

> Device events update their target immediately. Time-only changes for unrelated devices are reconciled by the bounded periodic full-estate evaluation.

The existing 300-second periodic full-estate evaluation remains the correctness backstop. Track 3C does not add a debounce timer, background evaluation worker, queue, or asynchronous scheduler.

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

## Track 3C ingestion vs post-commit phases

Counters are captured at health-callback entry. At that point the ingestion transaction has already physically committed. Post-commit work is EvaluationCoordinator / incident persistence and any trailing assertion reads included in the measured operation.

| Operation | Ingestion executes | Ingestion commits | Post-commit executes | Post-commit commits | Total executes | Total commits |
|---|---:|---:|---:|---:|---:|---:|
| Compact payload | 7 | 1 | 29 | 2 | 36 | 3 |
| Beast payload | 7 | 1 | 55 | 2 | 62 | 3 |
| Compact availability | 6 | 1 | 40 | 7 | 46 | 8 |
| Beast availability | 6 | 1 | 69 | 7 | 75 | 8 |
| Compact inventory | 43 | 1 | 93 | 8 | 136 | 9 |
| Beast inventory | 334 | 2 | 629 | 25 | 963 | 27 |

## Track 3C total baseline table

| Operation | Fixture | State | Executes | Executemany | Commits | Rollbacks | Other | Top repeated category |
|---|---|---|---:|---:|---:|---:|---:|---|
| Availability change ingestion | compact | warm | 46 | 0 | 8 | 0 | 0 | transaction.commit (8) |
| Availability change ingestion | beast | warm | 75 | 0 | 8 | 0 | 0 | read.incidents (10) |
| Dashboard composition | compact | warm | 328 | 0 | 0 | 0 | 0 | read.incident_devices (88) |
| Dashboard composition | beast | warm | 3467 | 0 | 0 | 0 | 0 | read.incident_devices (2184) |
| Device detail | compact | warm | 57 | 0 | 0 | 0 | 0 | read.topology_nodes (12) |
| Devices inventory composition | compact | warm | 355 | 0 | 0 | 0 | 0 | read.incident_devices (80) |
| Devices inventory composition | beast | warm | 4169 | 0 | 0 | 0 | 0 | read.incident_devices (2132) |
| EvidenceGraphService.build | compact | warm | 99 | 0 | 0 | 0 | 0 | read.schema (27) |
| Incident detail | compact | warm | 62 | 0 | 0 | 0 | 0 | read.topology_nodes (12) |
| Incident list | compact | warm | 97 | 0 | 0 | 0 | 0 | read.devices (23) |
| Device inventory refresh | beast | warm | 963 | 0 | 27 | 0 | 0 | read.availability_changes (168) |
| Device inventory refresh | compact | warm | 136 | 0 | 9 | 0 | 0 | read.health_snapshots (22) |
| Ordinary MQTT payload ingestion | compact | warm | 36 | 0 | 3 | 0 | 0 | read.schema (4) |
| Ordinary MQTT payload ingestion | beast | warm | 62 | 0 | 3 | 0 | 0 | read.incidents (10) |
| Device report preview | compact | warm | 510 | 0 | 0 | 0 | 0 | read.incident_devices (110) |
| Full report preview | compact | warm | 798 | 0 | 0 | 0 | 0 | read.incident_devices (182) |
| Incident report preview | compact | warm | 639 | 0 | 0 | 0 | 0 | read.incident_devices (128) |
| Network report preview | compact | warm | 798 | 0 | 0 | 0 | 0 | read.incident_devices (182) |

## Top repeated normalized statement shapes

### availability_ingestion

- 5× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `INSERT INTO events ( id, network_id, ieee_address, event_type, severity, title, summary, incident_id, payload_json, occurred_at ) VALUES (?)`
- 3× `SELECT source_ieee FROM topology_links WHERE snapshot_id = ? AND target_ieee = ? LIMIT ?`
- 3× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 3× `INSERT INTO incident_devices (incident_id, network_id, ieee_address, role) VALUES (?)`

### availability_ingestion_beast

- 9× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?`
- 9× `SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE dedup_key = ? AND lifecycle_state IN (?) ORDER BY updated_at DESC LIMIT ?`
- 9× `INSERT INTO incident_devices (incident_id, network_id, ieee_address, role) VALUES (?)`
- 7× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?`

### dashboard

- 88× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?`
- 49× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 43× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 26× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 24× `SELECT COUNT(*) FROM devices`

### dashboard_beast

- 2184× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?`
- 250× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 236× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 170× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 169× `SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE lifecycle_state IN (?) ORDER BY CASE lifecycle_state WHEN ? THEN ? WHEN ? THEN ? ELSE ? END, updated_at DESC`

### device_detail

- 12× `SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address`
- 10× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 6× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 4× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?`
- 3× `SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?`

### devices

- 80× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?`
- 44× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 40× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 20× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 20× `SELECT COUNT(*) FROM devices`

### devices_beast

- 2132× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?`
- 336× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 328× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 164× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 164× `SELECT COUNT(*) FROM devices`

### evidence_graph

- 27× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 26× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 23× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 6× `SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id = ? ORDER BY d.friendly_name`
- 5× `SELECT ieee_address, from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND changed_at >= ? ORDER BY changed_at ASC`

### incident_detail

- 12× `SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address`
- 10× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 9× `SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id = ? AND d.ieee_address = ?`
- 7× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?`

### incident_list

- 22× `SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id = ? AND d.ieee_address = ?`
- 12× `SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address`
- 10× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?`
- 10× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 9× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`

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
- 2× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?`
- 2× `INSERT INTO metric_samples (network_id, ieee_address, metric_name, metric_value, sampled_at) VALUES (?)`
- 2× `INSERT INTO events ( id, network_id, ieee_address, event_type, severity, title, summary, incident_id, payload_json, occurred_at ) VALUES (?)`
- 2× `SELECT primary_health, severity, confidence, summary, flags_json, evidence_json, counter_evidence_json, limitations_json, captured_at FROM health_snapshots WHERE scope = ? AND network_id = ? AND ieee_address IS NULL ORDER BY captured_at DESC LIMIT ?`

### payload_ingestion_beast

- 9× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?`
- 9× `SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE dedup_key = ? AND lifecycle_state IN (?) ORDER BY updated_at DESC LIMIT ?`
- 7× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?`
- 3× `SELECT friendly_name FROM topology_nodes WHERE snapshot_id = ? AND ieee_address = ?`

### report_device

- 110× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?`
- 66× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 51× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 37× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 32× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`

### report_full

- 182× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?`
- 103× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 88× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 49× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 46× `SELECT COUNT(*) FROM devices`

### report_incident

- 128× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?`
- 79× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 60× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 47× `SELECT source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id = ?`
- 40× `SELECT ieee_address, friendly_name, node_type, depth, lqi FROM topology_nodes WHERE snapshot_id = ? ORDER BY node_type, ieee_address`

### report_network

- 182× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ?`
- 103× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 88× `SELECT network_id, ieee_address, ha_device_id, ha_device_name, area_id, area_name, entity_id, match_confidence, updated_at FROM ha_device_enrichment WHERE network_id = ? AND ieee_address = ?`
- 49× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 46× `SELECT COUNT(*) FROM devices`

## Filter-after-limit reproduction

The Beast fixture seeds more than 20 newer unrelated Home network events plus `older-target-device-event`, and more than 100 newer unrelated global events plus `older-target-incident-event`. Tests assert both target events are genuinely outside the current network/global limits. All fixture timestamps are at or before `2026-07-15T12:00:00+00:00`. Proposed later repository signatures are:

- `list_events_for_device(network_id: str, ieee_address: str, *, limit: int) -> list[dict]`
- `list_events_for_incident(incident_id: str, *, limit: int) -> list[dict]`

Track 3A/3B/3C do not fix those production queries.

## Limitations and next scope

Exact values are snapshots for planning only, not budgets. Track 3C reduces post-commit full-network reclassification for device-scoped MQTT events. It does not batch Dashboard reads, coalesce evaluations, transaction-wrap health/incident writes with ingestion, or start Track 3D query-shape work.
