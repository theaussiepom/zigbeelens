# Track 3G shared network evidence composition performance baseline

Base commit for Track 3A history: `09f10a8` (final merged Track 2 base). Track 3A instrumentation landed via `perf/query-baseline-instrumentation`. Track 3B atomic MQTT ingestion landed via `perf/atomic-mqtt-ingestion`. Track 3C incremental device evaluation landed via `perf/incremental-device-evaluation` (merge `98ab5c8`). Track 3D bulk Dashboard/Devices composition landed via `perf/bulk-composition-reads` (merge `e8a6611`). Track 3E paginated incident collections and Track 3F scope-first report composition preceded this track (Track 3F tip `89c07a9`, merge `8bde6c1`). This document records **Track 3G current totals** after request-local `NetworkEvidenceContext` reuse, and preserves **Track 3A–3F history** for comparison.

These are planning snapshots, not accepted performance budgets.

## Base behaviour evidence

Track 1 and Track 2 behaviour was confirmed before Track 3A changes: Device Story exposes `related_unresolved_incident_ids`, incident membership is separate from current-issue relevance, canonical coverage evidence is used, and EvaluationCoordinator owns coherent health → incident → dashboard sequencing.

Track 3B preserved those semantics with one `BEGIN IMMEDIATE` ingestion transaction. Track 3C preserved them with incremental target-device evaluation after commit. Track 3D preserves them again: read composition uses request-local immutable contexts only; Device Story related incident IDs remain contextual; write-path authority and incremental evaluation are unchanged. Health evaluation runs before Devices/Dashboard freeze incident-sensitive context, and one ActiveIncidentReadContext projects both affected keys and related IDs. Track 3E keeps those rules while making public incident collections page-bounded: Device Story badges are composed only for devices on the returned page, and list rows do not load incident timelines.

## Consistency rule

> Device events update their target immediately. Time-only changes for unrelated devices are reconciled by the bounded periodic full-estate evaluation.

The existing 300-second periodic full-estate evaluation remains the correctness backstop. Track 3E/3F/3G do not add caches, debounce timers, or shared mutable cross-request state. Track 3G introduces only request-local immutable `NetworkEvidenceContext` values constructed by the composition orchestrator.

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
| History | Compact estate + 1500 incidents | Compact fixture plus 1500 additional incidents (mostly resolved, mixed open/watching), equal `updated_at` ties, zero-device incidents, missing-device refs, multi-network refs, and large affected-device sets. Used only for Track 3E collection scaling gates. |

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
| Devices Compact | 355 | 82 | -273 | read.incident_devices N+1 |
| Devices Beast | 4169 | 405 | -3764 | read.incident_devices N+1 |
| Incident list | 97 | 51 | -46 | per-incident device/event loads |
| Incident detail | 62 | 47 | -15 | global list_events filter-after-limit |
| Device detail | 57 | 54 | -3 | network list_events filter-after-limit |
| Full report preview | 798 | 262 | -536 | read.incident_devices N+1 |
| Network report preview | 798 | 262 | -536 | read.incident_devices N+1 |
| Incident report preview | 639 | 317 | -322 | read.incident_devices N+1 |
| Device report preview | 510 | 237 | -273 | read.incident_devices N+1 |
| EvidenceGraphService.build | 99 | 99 | 0 | unchanged (no topology rewrite) |

## Track 3C ingestion vs post-commit phases (historical)

Counters are captured at health-callback entry. At that point the ingestion transaction has already physically committed. Post-commit work is EvaluationCoordinator / incident persistence and any trailing assertion reads included in the measured operation. These rows are the Track 3C tip before later `incident_networks` maintenance and Track 3G HA bulk reuse on post-commit paths. Ingestion execute/commit counts remain the Track 3B/3C authority; see current `EXPECTED_PHASE_BASELINES` / Track 3G tip table for tip post-commit totals.

| Operation | Ingestion executes | Ingestion commits | Post-commit executes | Post-commit commits | Total executes | Total commits |
|---|---:|---:|---:|---:|---:|---:|
| Compact payload | 7 | 1 | 29 | 2 | 36 | 3 |
| Beast payload | 7 | 1 | 55 | 2 | 62 | 3 |
| Compact availability | 6 | 1 | 40 | 7 | 46 | 8 |
| Beast availability | 6 | 1 | 69 | 7 | 75 | 8 |
| Compact inventory | 43 | 1 | 93 | 8 | 136 | 9 |
| Beast inventory | 334 | 2 | 629 | 25 | 963 | 27 |

## Track 3G ingestion vs post-commit phases

Ingestion-phase execute and commit counts are unchanged from Track 3B/3C. Post-commit totals can drop when request-local bulk HA enrichment reuse removes repeated `get_ha_device_enrichment` / schema checks during evaluation-adjacent reads; that does not change the ingestion transaction boundary. Do not treat ingestion-phase stability alone as proof that Track 3B/3C totals are unchanged.

| Operation | Ingestion executes | Ingestion commits | Post-commit executes | Post-commit commits | Total executes | Total commits |
|---|---:|---:|---:|---:|---:|---:|
| Compact payload | 7 | 1 | 27 | 2 | 34 | 3 |
| Beast payload | 7 | 1 | 51 | 2 | 58 | 3 |
| Compact availability | 6 | 1 | 38 | 7 | 44 | 8 |
| Beast availability | 6 | 1 | 67 | 7 | 73 | 8 |
| Compact inventory | 43 | 1 | 93 | 8 | 136 | 9 |
| Beast inventory | 334 | 2 | 625 | 25 | 959 | 27 |


## Track 3E total baseline table (historical)

Preserved Track 3E tip totals before scope-first report composition. Report compact executes: Full 262, Network 262, Incident 317, Device 237.

| Operation | Fixture | State | Executes | Notes |
|---|---|---|---:|---|
| Full report preview | compact | warm | 262 | filter-after-dashboard |
| Network report preview | compact | warm | 262 | same shape as Full on single-network fixture |
| Incident report preview | compact | warm | 317 | complete-history debt seam |
| Device report preview | compact | warm | 237 | inventory fallback possible |

## Track 3G total baseline table

| Operation | Fixture | State | Executes | Executemany | Commits | Rollbacks | Other | Top repeated category |
|---|---|---|---:|---:|---:|---:|---:|---|
| Availability change ingestion | compact | warm | 44 | 0 | 8 | 0 | 0 | transaction.commit (8) |
| Availability change ingestion | beast | warm | 73 | 0 | 8 | 0 | 0 | read.incidents (10) |
| Dashboard composition | compact | warm | 22 | 0 | 0 | 0 | 0 | read.networks (3) |
| Dashboard composition | beast | warm | 25 | 0 | 0 | 0 | 0 | read.schema (4) |
| Device detail | compact | warm | 29 | 0 | 0 | 0 | 0 | read.networks (4) |
| Devices inventory composition | compact | warm | 57 | 0 | 0 | 0 | 0 | read.availability_changes (22) |
| Devices inventory composition | beast | warm | 345 | 0 | 0 | 0 | 0 | read.availability_changes (166) |
| EvidenceGraphService.build | compact | warm | 11 | 0 | 0 | 0 | 0 | read.schema (2) |
| Incident detail | compact | warm | 23 | 0 | 0 | 0 | 0 | read.availability_changes (5) |
| Incident list | compact | warm | 27 | 0 | 0 | 0 | 0 | read.availability_changes (7) |
| Incident list history | history | warm | 93 | 0 | 0 | 0 | 0 | read.availability_changes (40) |
| Device inventory refresh | beast | warm | 959 | 0 | 27 | 0 | 0 | read.availability_changes (168) |
| Device inventory refresh | compact | warm | 136 | 0 | 9 | 0 | 0 | read.health_snapshots (22) |
| Ordinary MQTT payload ingestion | compact | warm | 34 | 0 | 3 | 0 | 0 | read.networks (3) |
| Ordinary MQTT payload ingestion | beast | warm | 58 | 0 | 3 | 0 | 0 | read.incidents (10) |
| Device report preview | compact | warm | 32 | 0 | 0 | 0 | 0 | read.devices (5) |
| Device report preview | history | warm | 32 | 0 | 0 | 0 | 0 | read.devices (5) |
| Full report preview | compact | warm | 67 | 0 | 0 | 0 | 0 | read.availability_changes (22) |
| Full report preview | beast | warm | 358 | 0 | 0 | 0 | 0 | read.availability_changes (166) |
| Incident report preview | compact | warm | 56 | 0 | 0 | 0 | 0 | read.incidents (9) |
| Incident report preview | history | warm | 56 | 0 | 0 | 0 | 0 | read.incidents (9) |
| Network report preview | compact | warm | 67 | 0 | 0 | 0 | 0 | read.availability_changes (22) |
| Network report preview | beast | warm | 267 | 0 | 0 | 0 | 0 | read.availability_changes (122) |

## Track 3F total baseline table (historical)

| Operation | Fixture | State | Executes | Executemany | Commits | Rollbacks | Other | Top repeated category |
|---|---|---|---:|---:|---:|---:|---:|---|
| Availability change ingestion | compact | warm | 48 | 0 | 8 | 0 | 0 | transaction.commit (8) |
| Availability change ingestion | beast | warm | 77 | 0 | 8 | 0 | 0 | read.incidents (10) |
| Dashboard composition | compact | warm | 110 | 0 | 0 | 0 | 0 | read.schema (30) |
| Dashboard composition | beast | warm | 282 | 0 | 0 | 0 | 0 | read.schema (87) |
| Device detail | compact | warm | 55 | 0 | 0 | 0 | 0 | read.topology_nodes (12) |
| Devices inventory composition | compact | warm | 83 | 0 | 0 | 0 | 0 | read.availability_changes (22) |
| Devices inventory composition | beast | warm | 405 | 0 | 0 | 0 | 0 | read.availability_changes (168) |
| EvidenceGraphService.build | compact | warm | 99 | 0 | 0 | 0 | 0 | read.schema (27) |
| Incident detail | compact | warm | 48 | 0 | 0 | 0 | 0 | read.topology_nodes (12) |
| Incident list | compact | warm | 52 | 0 | 0 | 0 | 0 | read.topology_nodes (12) |
| Incident list history | history | warm | 131 | 0 | 0 | 0 | 0 | read.availability_changes (42) |
| Device inventory refresh | beast | warm | 967 | 0 | 27 | 0 | 0 | read.availability_changes (168) |
| Device inventory refresh | compact | warm | 138 | 0 | 9 | 0 | 0 | read.health_snapshots (22) |
| Ordinary MQTT payload ingestion | compact | warm | 36 | 0 | 3 | 0 | 0 | read.schema (4) |
| Ordinary MQTT payload ingestion | beast | warm | 62 | 0 | 3 | 0 | 0 | read.incidents (10) |
| Device report preview | compact | warm | 151 | 0 | 0 | 0 | 0 | read.schema (36) |
| Device report preview | history | warm | 151 | 0 | 0 | 0 | 0 | read.schema (36) |
| Full report preview | compact | warm | 187 | 0 | 0 | 0 | 0 | read.schema (36) |
| Full report preview | beast | warm | 663 | 0 | 0 | 0 | 0 | read.availability_changes (178) |
| Incident report preview | compact | warm | 175 | 0 | 0 | 0 | 0 | read.schema (36) |
| Incident report preview | history | warm | 175 | 0 | 0 | 0 | 0 | read.schema (36) |
| Network report preview | compact | warm | 187 | 0 | 0 | 0 | 0 | read.schema (36) |
| Network report preview | beast | warm | 421 | 0 | 0 | 0 | 0 | read.availability_changes (127) |



## Track 3E → Track 3F report execute comparison

Scope-first composition removes complete-history / full-dashboard assembly for narrow reports. Compact fixture is single-network, so Full and Network remain similar there; Beast proves Network << Full. Ingestion commit counts and ingestion-phase execute counts remain at Track 3B/3C values. The Track 3F corrective pass removes candidate-loop `incident_networks` reads; remaining write cost maintains normalized identity.

| Operation | Track 3E executes | Track 3F executes | Delta | Main removed work |
|---|---:|---:|---:|---|
| Full report preview (compact) | 262 | 187 | -75 | scope-before-composition |
| Network report preview (compact) | 262 | 187 | -75 | scope-before-composition |
| Incident report preview (compact) | 317 | 175 | -142 | scope-before-composition |
| Device report preview (compact) | 237 | 151 | -86 | scope-before-composition |
| Network report preview (beast) | — | 421 | — | Home-only scope |
| Full report preview (beast) | — | 663 | — | estate-wide Full scope |
| Incident report (history) | — | 175 | — | unrelated history ignored |
| Device report (history) | — | 151 | — | unrelated history ignored |

Remaining repeated `read.topology_*` / Device Story network-context loads on in-scope networks are Track 3G debt (shared topology composition), not hidden filter-after-composition.


## Track 3F → Track 3G execute comparison

| Operation | Track 3F executes | Track 3G executes | Delta | Main removed work |
|---|---:|---:|---:|---|
| Dashboard composition (compact) | 110 | 22 | -88 | shared NetworkEvidenceContext |
| Dashboard composition (beast) | 282 | 25 | -257 | shared NetworkEvidenceContext |
| Devices inventory (compact) | 83 | 57 | -26 | shared NetworkEvidenceContext |
| Devices inventory (beast) | 405 | 345 | -60 | shared NetworkEvidenceContext |
| EvidenceGraphService.build | 99 | 11 | -88 | shared NetworkEvidenceContext |
| Full report preview (compact) | 187 | 67 | -120 | shared NetworkEvidenceContext |
| Full report preview (beast) | 663 | 358 | -305 | shared NetworkEvidenceContext |
| Network report preview (compact) | 187 | 67 | -120 | shared NetworkEvidenceContext |
| Network report preview (beast) | 421 | 267 | -154 | shared NetworkEvidenceContext |
| Incident report preview | 175 | 56 | -119 | shared NetworkEvidenceContext |
| Device report preview | 151 | 32 | -119 | shared NetworkEvidenceContext |
| Incident list | 52 | 27 | -25 | shared NetworkEvidenceContext (+1 complete inventory) |
| Device detail | 55 | 29 | -26 | Device Story NetworkEvidenceContext |

Duplicate topology snapshot/node/link and availability scans across Device Story, Evidence Graph, Dashboard, and Reports are collapsed into one request-local context per network. Remaining Devices/Device Detail cost is dominated by per-device availability-history and device-snapshot reads outside Track 3G topology ownership. The corrective pass loads complete network inventories for Incident/Device subject scopes (bounded one-network inventory read), which can add a small execute count versus an incorrect subject-as-inventory baseline.

Track 3E → Track 3G report execute deltas (compact):

| Track 3E executes | Track 3G executes | Delta |
|---:|---:|---:|
| 262 | 67 | -195 |
| 262 | 67 | -195 |
| 317 | 56 | -261 |
| 237 | 32 | -205 |

## Track 3E collection scaling

Public incident list cost must scale with page size and unique devices on that page, not stored incident history. Against the History fixture (1505 incidents), a `limit=50` page measures 130 executes with one bulk incident-device read and zero incident timeline event reads. Compact list remains 51 executes. Single-status history pages (including resolved-only) also avoid a full matching-set temporary ORDER BY sort via the dynamic production ORDER BY helper.

## Track 3E collection ORDER BY index evidence

Migration `010` creates expression index `idx_incidents_collection_order` on the lifecycle-rank expression plus `updated_at DESC, id DESC`. Page filters use the same `CASE lifecycle_state … END` ranks so SQLite can consume that index. Count still filters on `lifecycle_state` and may use `idx_incidents_lifecycle`.

Production ORDER BY is dynamic:

- single lifecycle status → `ORDER BY updated_at DESC, id DESC` (rank is constant; omitting it avoids a temporary sort)
- multiple statuses → `ORDER BY lifecycle-rank ASC, updated_at DESC, id DESC`

Measured `EXPLAIN QUERY PLAN` against the production page SELECT (300-row synthetic estate):

| Query class | Plan | Temp ORDER BY B-tree |
|---|---|---|
| open only first page | `SEARCH incidents USING INDEX idx_incidents_collection_order (<expr>=?)` | no |
| watching only first page | `SEARCH incidents USING INDEX idx_incidents_collection_order (<expr>=?)` | no |
| resolved only first page | `SEARCH incidents USING INDEX idx_incidents_collection_order (<expr>=?)` | no |
| open / watching / resolved cursor continuation | `SEARCH incidents USING INDEX idx_incidents_collection_order (<expr>=?)` | no |
| default all-status first page | `SEARCH incidents USING INDEX idx_incidents_collection_order (<expr>=?)` | no |
| open + watching | `SEARCH incidents USING INDEX idx_incidents_collection_order (<expr>=?)` | no |
| updated_after | `SEARCH … idx_incidents_collection_order (<expr>=? AND updated_at>?)` | no |
| network-scoped | collection-order index + `incident_devices` EXISTS covering PK | no |
| device-scoped | collection-order index + `incident_devices` EXISTS covering PK | no |

No page class above may contain `USE TEMP B-TREE FOR ORDER BY`.

## Top repeated normalized statement shapes

### availability_ingestion
- 3× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `INSERT INTO events ( id, network_id, ieee_address, event_type, severity, title, summary, incident_id, payload_json, occurred_at ) VALUES (?)`
- 3× `SELECT source_ieee FROM topology_links WHERE snapshot_id = ? AND target_ieee = ? LIMIT ?`
- 3× `INSERT INTO incident_devices (incident_id, network_id, ieee_address, role) VALUES (?)`
- 2× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ? ORDER BY network_id, ieee_address, role`

### availability_ingestion_beast
- 9× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ? ORDER BY network_id, ieee_address, role`
- 9× `WITH selected AS ( SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE dedup_key = ? AND lifecycle_state IN (?) ORDER BY updated_at DESC LIMIT ? ) SELECT s.id, s.incident_type, s.lifecycle_state, s.severity, s.scope, s.confidence, s.title, s.summary, s.explanation, s.evidence_json, s.counter_evidence_json, s.limitations_json, s.opened_at, s.updated_at, s.resolved_at, s.dedup_key, n.network_id FROM selected s LEFT JOIN incident_networks n ON n.incident_id = s.id ORDER BY n.network_id`
- 9× `INSERT INTO incident_devices (incident_id, network_id, ieee_address, role) VALUES (?)`
- 5× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?`

### dashboard
- 3× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 3× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 2× `SELECT COUNT(*) FROM devices`
- 2× `WITH requested(network_id, ieee_address) AS (VALUES (?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?)) SELECT h.network_id, h.ieee_address, h.ha_device_id, h.ha_device_name, h.area_id, h.area_name, h.entity_id, h.match_confidence, h.updated_at FROM requested r JOIN ha_device_enrichment h ON h.network_id = r.network_id AND h.ieee_address = r.ieee_address ORDER BY h.network_id, h.ieee_address`
- 1× `SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address ORDER BY d.network_id, d.friendly_name`

### dashboard_beast
- 4× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 2× `SELECT COUNT(*) FROM devices`
- 2× `SELECT coordinator_ieee, channel, pan_id, extended_pan_id, payload_json, captured_at FROM bridge_snapshots WHERE network_id = ? ORDER BY captured_at DESC LIMIT ?`
- 2× `WITH requested(network_id, ieee_address) AS (VALUES (?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?)) SELECT h.network_id, h.ieee_address, h.ha_device_id, h.ha_device_name, h.area_id, h.area_name, h.entity_id, h.match_confidence, h.updated_at FROM requested r JOIN ha_device_enrichment h ON h.network_id = r.network_id AND h.ieee_address = r.ieee_address ORDER BY h.network_id, h.ieee_address`

### device_detail
- 3× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 2× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 2× `SELECT COUNT(*) FROM devices`
- 2× `SELECT DISTINCT i.id FROM incidents i JOIN incident_devices d ON d.incident_id = i.id WHERE d.network_id = ? AND d.ieee_address = ? AND i.lifecycle_state IN (?) ORDER BY i.updated_at DESC, i.id DESC`
- 2× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`

### devices
- 20× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 20× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 2× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 2× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 1× `SELECT COUNT(*) FROM devices`

### devices_beast
- 164× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 164× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 2× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 2× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 1× `SELECT COUNT(*) FROM devices`

### evidence_graph
- 2× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 1× `SELECT id, name, base_topic, bridge_state FROM networks WHERE id = ?`
- 1× `SELECT d.network_id, d.ieee_address, d.friendly_name, d.device_type, d.power_source, d.manufacturer, d.model, d.interview_state, COALESCE(s.availability, ?) AS availability, s.last_seen, s.last_payload_at, s.linkquality, s.battery FROM devices d LEFT JOIN device_current_state s ON d.network_id = s.network_id AND d.ieee_address = s.ieee_address WHERE d.network_id IN (?) ORDER BY d.network_id ASC, d.friendly_name ASC`
- 1× `SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id IN (?) ORDER BY network_id ASC, captured_at DESC`
- 1× `SELECT snapshot_id, source_ieee, target_ieee, source_type, target_type, linkquality, depth, relationship, route_count FROM topology_links WHERE snapshot_id IN (?) ORDER BY snapshot_id ASC`

### incident_detail
- 3× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 3× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 2× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 1× `SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE id = ?`
- 1× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id IN (?) ORDER BY incident_id, network_id, ieee_address, role`

### incident_list
- 5× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 5× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 2× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 1× `SELECT COUNT(*) AS n FROM incidents WHERE lifecycle_state IN (?)`
- 1× `SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE CASE lifecycle_state WHEN ? THEN ? WHEN ? THEN ? ELSE ? END IN (?) ORDER BY CASE lifecycle_state WHEN ? THEN ? WHEN ? THEN ? ELSE ? END ASC, updated_at DESC, id DESC LIMIT ?`

### incident_list_history
- 38× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 38× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 2× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 1× `SELECT COUNT(*) AS n FROM incidents WHERE lifecycle_state IN (?)`
- 1× `SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE CASE lifecycle_state WHEN ? THEN ? WHEN ? THEN ? ELSE ? END IN (?) ORDER BY CASE lifecycle_state WHEN ? THEN ? WHEN ? THEN ? ELSE ? END ASC, updated_at DESC, id DESC LIMIT ?`

### inventory_ingestion_beast
- 164× `INSERT INTO devices ( network_id, ieee_address, friendly_name, device_type, power_source, manufacturer, model, interview_state, created_at, updated_at ) VALUES (?) ON CONFLICT(network_id, ieee_address) DO UPDATE SET friendly_name = excluded.friendly_name, device_type = excluded.device_type, power_source = excluded.power_source, manufacturer = COALESCE(excluded.manufacturer, devices.manufacturer), model = COALESCE(excluded.model, devices.model), interview_state = excluded.interview_state, updated_at = excluded.updated_at`
- 164× `INSERT OR IGNORE INTO device_current_state (network_id, ieee_address) VALUES (?)`
- 164× `SELECT COUNT(*) FROM availability_changes WHERE network_id = ? AND ieee_address = ? AND changed_at >= ?`
- 164× `SELECT primary_health, severity, confidence, summary, flags_json, evidence_json, counter_evidence_json, limitations_json, captured_at FROM health_snapshots WHERE scope = ? AND network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 49× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`

### inventory_ingestion_compact
- 20× `INSERT INTO devices ( network_id, ieee_address, friendly_name, device_type, power_source, manufacturer, model, interview_state, created_at, updated_at ) VALUES (?) ON CONFLICT(network_id, ieee_address) DO UPDATE SET friendly_name = excluded.friendly_name, device_type = excluded.device_type, power_source = excluded.power_source, manufacturer = COALESCE(excluded.manufacturer, devices.manufacturer), model = COALESCE(excluded.model, devices.model), interview_state = excluded.interview_state, updated_at = excluded.updated_at`
- 20× `INSERT OR IGNORE INTO device_current_state (network_id, ieee_address) VALUES (?)`
- 20× `SELECT COUNT(*) FROM availability_changes WHERE network_id = ? AND ieee_address = ? AND changed_at >= ?`
- 20× `SELECT primary_health, severity, confidence, summary, flags_json, evidence_json, counter_evidence_json, limitations_json, captured_at FROM health_snapshots WHERE scope = ? AND network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 7× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`

### payload_ingestion
- 3× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 2× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ? ORDER BY network_id, ieee_address, role`
- 2× `INSERT INTO metric_samples (network_id, ieee_address, metric_name, metric_value, sampled_at) VALUES (?)`
- 2× `INSERT INTO events ( id, network_id, ieee_address, event_type, severity, title, summary, incident_id, payload_json, occurred_at ) VALUES (?)`
- 2× `SELECT primary_health, severity, confidence, summary, flags_json, evidence_json, counter_evidence_json, limitations_json, captured_at FROM health_snapshots WHERE scope = ? AND network_id = ? AND ieee_address IS NULL ORDER BY captured_at DESC LIMIT ?`

### payload_ingestion_beast
- 9× `SELECT incident_id, network_id, ieee_address, role FROM incident_devices WHERE incident_id = ? ORDER BY network_id, ieee_address, role`
- 9× `WITH selected AS ( SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE dedup_key = ? AND lifecycle_state IN (?) ORDER BY updated_at DESC LIMIT ? ) SELECT s.id, s.incident_type, s.lifecycle_state, s.severity, s.scope, s.confidence, s.title, s.summary, s.explanation, s.evidence_json, s.counter_evidence_json, s.limitations_json, s.opened_at, s.updated_at, s.resolved_at, s.dedup_key, n.network_id FROM selected s LEFT JOIN incident_networks n ON n.incident_id = s.id ORDER BY n.network_id`
- 5× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `SELECT snapshot_id, network_id, captured_at, requested_by, status, router_count, end_device_count, link_count, warning_acknowledged, error FROM topology_snapshots WHERE network_id = ? AND status = ? ORDER BY captured_at DESC LIMIT ?`
- 3× `SELECT friendly_name FROM topology_nodes WHERE snapshot_id = ? AND ieee_address = ?`

### report_device
- 4× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 2× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 2× `SELECT COUNT(*) FROM devices`
- 2× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 2× `SELECT COUNT(*) FROM topology_snapshots WHERE network_id IN (?)`

### report_device_history
- 4× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 2× `SELECT COUNT(*) FROM devices`
- 2× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 2× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 2× `SELECT COUNT(*) FROM topology_snapshots WHERE network_id IN (?)`

### report_full
- 20× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 20× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 4× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 2× `WITH requested(network_id, ieee_address) AS (VALUES (?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?)) SELECT h.network_id, h.ieee_address, h.ha_device_id, h.ha_device_name, h.area_id, h.area_name, h.entity_id, h.match_confidence, h.updated_at FROM requested r JOIN ha_device_enrichment h ON h.network_id = r.network_id AND h.ieee_address = r.ieee_address ORDER BY h.network_id, h.ieee_address`

### report_full_beast
- 164× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 164× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 5× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 3× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 2× `WITH requested(network_id, ieee_address) AS (VALUES (?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?)) SELECT h.network_id, h.ieee_address, h.ha_device_id, h.ha_device_name, h.area_id, h.area_name, h.entity_id, h.match_confidence, h.updated_at FROM requested r JOIN ha_device_enrichment h ON h.network_id = r.network_id AND h.ieee_address = r.ieee_address ORDER BY h.network_id, h.ieee_address`

### report_incident
- 6× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 5× `SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE id = ?`
- 4× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 4× `SELECT COUNT(*) FROM devices`
- 4× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`

### report_incident_history
- 6× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 5× `SELECT id, incident_type, lifecycle_state, severity, scope, confidence, title, summary, explanation, evidence_json, counter_evidence_json, limitations_json, opened_at, updated_at, resolved_at, dedup_key FROM incidents WHERE id = ?`
- 4× `SELECT COUNT(*) FROM devices`
- 4× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`
- 4× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`

### report_network
- 20× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 20× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 4× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 2× `WITH requested(network_id, ieee_address) AS (VALUES (?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?),(?, ?)) SELECT h.network_id, h.ieee_address, h.ha_device_id, h.ha_device_name, h.area_id, h.area_name, h.entity_id, h.match_confidence, h.updated_at FROM requested r JOIN ha_device_enrichment h ON h.network_id = r.network_id AND h.ieee_address = r.ieee_address ORDER BY h.network_id, h.ieee_address`
- 2× `SELECT COUNT(*) FROM topology_snapshots WHERE network_id IN (?)`

### report_network_beast
- 120× `SELECT availability, last_seen, last_payload_at, linkquality, battery, captured_at FROM device_snapshots WHERE network_id = ? AND ieee_address = ? ORDER BY captured_at DESC LIMIT ?`
- 120× `SELECT from_state, to_state, changed_at FROM availability_changes WHERE network_id = ? AND ieee_address = ? ORDER BY changed_at DESC LIMIT ?`
- 4× `SELECT ? FROM sqlite_master WHERE type=? AND name=?`
- 2× `SELECT COUNT(*) FROM topology_snapshots WHERE network_id IN (?)`
- 1× `SELECT id, name, base_topic, bridge_state FROM networks ORDER BY name`

## Track 3F corrective hot-path incident_networks

Measured `read.incident_networks` / `write.incident_networks` after the corrective pass:

| Surface | read.incident_networks | write.incident_networks |
|---|---:|---:|
| availability_ingestion | 0 | 2 |
| availability_ingestion_beast | 0 | 2 |
| dashboard | 1 | 0 |
| dashboard_beast | 1 | 0 |
| device_detail | 1 | 0 |
| devices | 1 | 0 |
| devices_beast | 1 | 0 |
| evidence_graph | 0 | 0 |
| incident_detail | 1 | 0 |
| incident_list | 1 | 0 |
| incident_list_history | 1 | 0 |
| inventory_ingestion_beast | 0 | 4 |
| inventory_ingestion_compact | 0 | 2 |
| payload_ingestion | 0 | 0 |
| payload_ingestion_beast | 0 | 0 |
| report_device | 0 | 0 |
| report_device_history | 0 | 0 |
| report_full | 1 | 0 |
| report_full_beast | 1 | 0 |
| report_incident | 2 | 0 |
| report_incident_history | 2 | 0 |
| report_network | 1 | 0 |
| report_network_beast | 1 | 0 |

Dashboard/Devices/Incident list retain a bounded one-query active-context identity read (`read.incident_networks = 1`). Lifecycle evaluation no longer issues per-candidate `list_incident_networks` reads (`read.incident_networks = 0` on payload/availability/inventory ingest). Necessary writes remain when candidate network identity changes (`write.incident_networks` 2–4 on availability/inventory paths).
