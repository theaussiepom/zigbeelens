# Phase 7A investigation — measurement and final disposition

Branch `perf/release-query-bounds`. Distinguishes:

1. **Track 5 historical** — frozen tip before Phase 7A;
2. **Initial Phase 7A attempt** — bulk latest-complete via history-wide `ROW_NUMBER`, statement-count device-history claims;
3. **Final Phase 7A bounded production paths** — indexed latest seeks, row/link-bounded device history, History full/network report ops, strict cursor versions, SQLite 3.34.1 runtime smoke.

## Environment

| Item | Value |
|---|---|
| Command | `cd apps/core && uv run pytest -q tests/performance` |
| Python | 3.14.x (host) |
| Host SQLite | 3.53.x |
| Smoke SQLite | **3.34.1** via `python:3.12-slim-bullseye` |
| Phase 7A merge base | `4595edd22e3a0cc8fba236493b0f2cbe995b9728` |

## Candidates and final disposition

### 1. Overview recent changes (PR #83) — retained

- Additive `order=recent` (`updated_at DESC, id DESC`); Overview passes `order=recent`.
- Default lifecycle order unchanged; lifecycle v1 cursors byte-compatible.
- Cursor versions must be exact `int` in `{1, 2}` (reject bool/float/str/null).

### 2. Latest topology — final: indexed seek

- **Initial 7A:** one chunked statement with `ROW_NUMBER() OVER (PARTITION BY network_id …)` over all complete snapshots for requested IDs (still proportional to retained history).
- **Final 7A:** `WITH requested(network_id) AS (VALUES …)` + correlated `ORDER BY captured_at DESC, snapshot_id DESC LIMIT 1` seek per network; single-network method restored to the same indexed `LIMIT 1` query.
- Proofs: 1-vs-1000 retained snapshots same statement count; 2-vs-40 networks same chunk statement count; EXPLAIN selects `idx_topology_snapshots_latest_complete`; no TEMP B-TREE; no `ROW_NUMBER`.

### 3. Device snapshot history — final: target-bounded endpoint

- Exact entry point: `build_device_snapshot_history_response`.
- Loads at most `MAX_SNAPSHOT_HISTORY` complete snapshots; comparison links only for those IDs (target-device scoped); latest nodes/links once.
- Does **not** call `list_devices` / `list_devices_for_networks`. Network-level tracking uses:
  - earliest transition, else
  - `network_has_explicit_availability_state` (`SELECT 1 … availability IN ('online','offline') LIMIT 1`).
- Target `DeviceRow` fetched once; `has_current_issue` remains target-offline only.
- Deep equality vs the former broad `EVIDENCE_GRAPH_FACTS_REQUIREMENTS` path is proven in the Phase 7A matrix (including topology_facts).

### 4. Topology link indexes

- `idx_topology_links_snapshot_source` — **rejected** (PK covers source seeks).
- `idx_topology_links_snapshot_target` — **required** for the multi-snapshot device-history query after rewriting to `UNION ALL` (source branch → PK; target branch → this index; no TEMP B-TREE). The OR form either ignores the target index or introduces `USE TEMP B-TREE FOR ORDER BY`.

### 5. Metric sample window — retained

- `ORDER BY sampled_at DESC, id DESC` + `idx_metric_samples_device_time`.

### 6. Shared availability grouping — retained

- Offline-transition SQL for `_instability_events` + `idx_availability_changes_offline_since`.

### 7. Reports — History full/network measured

| Operation | Fixture | Executes | Commits |
|---|---|---:|---:|
| `report_full_history` | history | 40 | 0 |
| `report_network_history` | history | 39 | 0 |
| `report_incident_history` | history | 40 | 0 |
| `report_device_history` | history | 29 | 0 |

No per-incident / per-device query loops; timeline/metrics/availability remain SQL-limited. History fixture syncs/warms the office network so full-estate composition maps every device.

## Index disposition (migration 013)

| Index | Disposition |
|---|---|
| `idx_incidents_recent_order` | **required** — recent first page / cursor / `updated_after` |
| `idx_topology_snapshots_latest_complete` | **required** — indexed latest-complete seek |
| `idx_metric_samples_device_time` | **required** — mixed-metric newest-N |
| `idx_availability_changes_offline_since` | **required** — offline lookback |
| `idx_topology_links_snapshot_source` | **rejected** — PK sufficient for source seeks |
| `idx_topology_links_snapshot_target` | **required** — target branch of device-history `UNION ALL` |

## SQLite 3.34.1 smoke

Runtime proof (not host-version assertion alone):

- v12 → v13 migration + rerun;
- `PRAGMA quick_check` / `foreign_key_check`;
- recent incident first/cursor page;
- bulk latest topology query;
- metric window;
- offline-transition query.

See `tests/performance/test_sqlite_3_34_1_smoke.py` evidence and Docker smoke output.
