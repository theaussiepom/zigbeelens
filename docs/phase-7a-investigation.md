# Phase 7A investigation — pre-change measurement

Recorded before production query changes on branch `perf/release-query-bounds`.

## Environment

| Item | Value |
|---|---|
| Command | `cd apps/core && uv run pytest -q tests/performance` |
| Result | **47 passed** |
| Python | 3.14.5 |
| Host SQLite | 3.53.2 |
| Base HEAD | `4595edd22e3a0cc8fba236493b0f2cbe995b9728` (Phase 6D merge of tip `125f94b`) |

## Candidates

### 1. Overview recent changes (PR #83)

- **Fault:** `/api/incidents?updated_after=…&limit=50` uses lifecycle-ranked order, so newer watching/resolved updates can be omitted when ≥50 older open incidents match the filter.
- **Fixture:** >50 open incidents updated after cutoff, older than newer watching/resolved rows; equal `updated_at` ties; multi-page estate.
- **Correction:** additive `order=recent` (`updated_at DESC, id DESC`) with separate recent cursor; Overview passes `order=recent`.
- **Invariants:** default lifecycle order unchanged; lifecycle cursors byte-compatible; no Python page sort; keyset pagination only.

### 2. Topology overview N+1

- **Fault:** `_network_summaries` / `topology_status_dict` call `get_latest_topology_snapshot` once per network.
- **Correction:** `get_latest_topology_snapshots_for_networks` (chunked, one `_has_table` check).
- **Invariants:** complete-only latest semantics; network order; payload shape.

### 3. Device snapshot history

- **Fault:** load all snapshots then slice; one `list_topology_links` per usable snapshot when links not preloaded.
- **Correction:** SQL-limited complete snapshots + bulk links for selected IDs.
- **Invariants:** `MAX_SNAPSHOT_HISTORY` window; topology facts parity.

### 4. Topology link source/target plans

- **Candidate indexes:** `(snapshot_id, source_ieee)`, `(snapshot_id, target_ieee)`.
- **Gate:** add only when production EXPLAIN selects them without TEMP B-TREE / full scan.

### 5. Metric sample window

- **Fault risk:** mixed-metric newest-N without deterministic `id` tie-break; name-leading index may not cover the query.
- **Correction:** `ORDER BY sampled_at DESC, id DESC`; device-time index only if EXPLAIN requires it.

### 6. Shared availability grouping

- **Finding:** `_instability_events` consumes only `to_state = 'offline'`.
- **Correction:** dedicated offline-transition SQL read for the default path; model-pattern / other consumers keep full transitions.
- **Invariants:** no arbitrary count cap; lookback unchanged.

### 7. Reports

- Measure Compact/Beast/History scopes for N+1 and configured SQL limits; do not shrink ReportDetailV3 contents.

## Index disposition

| Index | Disposition |
|---|---|
| `idx_incidents_recent_order` | **required** — recent first page / cursor / `updated_after` |
| `idx_topology_snapshots_latest_complete` | **required** — bulk latest-complete |
| `idx_metric_samples_device_time` | **required** — mixed-metric newest-N |
| `idx_availability_changes_offline_since` | **required** — offline lookback |
| `idx_topology_links_snapshot_source` | **rejected** — PK `(snapshot_id, source_ieee, target_ieee)` already covers |
| `idx_topology_links_snapshot_target` | **rejected** — production EXPLAIN prefers PK prefix on `snapshot_id` |
