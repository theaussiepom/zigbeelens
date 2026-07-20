# HTTP API

ZigbeeLens Core exposes a read-only JSON API for the dashboard, Home Assistant integration, and external tools.

## API prefix

**`/api/v1` is the preferred prefix for new integrations.**

Existing `/api/*` routes remain available for backward compatibility. Both prefixes serve the same handlers.

| Preferred (v1) | Legacy alias |
|----------------|--------------|
| `GET /api/v1/health` | `GET /api/health` |
| `GET /api/v1/dashboard` | `GET /api/dashboard` |
| `GET /api/v1/capabilities` | — |
| `GET /api/v1/status` | — |
| `GET /api/v1/events/stream` | `GET /api/events/stream` |
| `GET /api/v1/reports` | `GET /api/reports` |
| `GET /api/v1/storage/status` | `GET /api/storage/status` |

All other public routes under `/api/` are also mounted at `/api/v1/` (devices, incidents, networks, topology, enrichment, config status, version, scenarios).

## Authentication

Protected routes under `/api` and `/api/v1` accept `Authorization: Bearer <token>`, a valid browser session cookie, or (in `home_assistant_ingress` mode) a Supervisor-injected ingress identity from an exact trusted ASGI peer. Public endpoints are `GET /healthz`, `GET /api/version`, `GET /api/v1/version`, and `GET /api/auth/session` (plus `/api/v1` aliases; static UI may be proxy-only in add-on posture). Session login is `POST /api/auth/session` (bearer bootstrap). Cookie-authenticated mutations require an exact browser `Origin` and `X-ZigbeeLens-CSRF-Token`; ingress-authenticated mutations do not. Do not send `X-Remote-User-*` as a client credential — OpenAPI does not advertise those headers. See [security.md](security.md).

## Core endpoints

### Health

`GET /api/v1/health` — service health, database, collector summary, optional feature status (MQTT discovery, topology, HA enrichment). Collector errors are redacted.

### Capabilities

`GET /api/v1/capabilities` — stable feature flags for integrations (no secrets):

```json
{
  "product": "zigbeelens",
  "version": "0.1.0",
  "capabilities": {
    "dashboard": true,
    "sse": true,
    "reports": true,
    "mqtt_discovery": true,
    "home_assistant_enrichment": true,
    "topology": false,
    "mock_scenarios": true,
    "read_only_observability": true,
    "mqtt_collector": true
  }
}
```

Boolean values reflect configured features, not live collector success.

### Status

`GET /api/v1/status` — high-level collector and storage status without sensitive configuration:

- MQTT collector connection and last message time
- Zigbee2MQTT bridge/coordinator observation per network
- Storage availability
- Last stored report timestamp (if any)

Use `/api/v1/config/status` for redacted configuration detail (MQTT server host with credentials masked).

### Dashboard

`GET /api/v1/dashboard` — full dashboard payload for the web UI and HACS companion panel.

Optional query: `scenario` (mock mode only).

### Live updates

`GET /api/v1/events/stream` — Server-Sent Events stream (heartbeat, dashboard updates, collector status).

### Reports

- `GET /api/v1/reports/preview` — generate preview without storing
- `POST /api/v1/reports` — generate and store
- `GET /api/v1/reports` — list stored reports
- `GET /api/v1/reports/{id}` — fetch stored report
- `GET /api/v1/reports/{id}/download` — download redacted export

See [reports.md](reports.md).

### Storage status

`GET /api/v1/storage/status` (legacy: `GET /api/storage/status`) — retention policy, last maintenance facts, SQLite footprint, and integrity check facts. Read-only; no purge/backup mutations.

| Block | Fields |
|-------|--------|
| `policy` | `policy_version`, `telemetry_retention_days`, `resolved_incident_retention_days` (`null` = keep indefinitely), `report_retention_days` (`null` = until manually deleted), `maintenance_interval_hours`, `topology_max_snapshots_per_network` |
| `maintenance` | `running`, timestamps (`last_started_at`, `last_completed_at`, `last_successful_at`, `next_scheduled_at`), `last_error_code`, `failure_category`, cutoffs, `rows_deleted_by_category`, `rows_updated_by_category`, malformed/future timestamp counts, `more_work_pending`, `duration_ms`, `wal_checkpoint` |
| `footprint` | `database_bytes`, `wal_bytes`, `shm_bytes`, `total_sqlite_bytes`, page/freelist/reusable sizes, `schema_version` |
| `integrity` | `startup_gates` (`quick_and_foreign_keys`), plus `quick_check` / `foreign_key_check` facts: `status`, `checked_at`, `violation_count` |

**Null totals before first success:** `maintenance.total_rows_deleted` (and related duration/cutoff fields when never written) stay `null` until a maintenance cycle has completed successfully and persisted status. Integrity check facts may also show `null` status/checked_at until the first startup gate run is stored.

Successful maintenance may publish SSE events: `storage_maintenance_completed`, and when categories change `incidents_updated`, `reports_updated`, `timeline_updated`, `topology_updated`. There is no HTTP backup or purge endpoint.

## Home Assistant integration

The HACS integration uses legacy `/api/health`, `/api/dashboard`, and related routes with an optional server-side `Authorization: Bearer` header (never in URLs). This remains supported. New HA-side code may adopt `/api/v1` when convenient.

See [hacs.md](hacs.md) and [hacs-embedded-view.md](hacs-embedded-view.md).

## Lens family alignment

ThreadLens uses the same `/api/v1` prefix pattern. Shared conventions: [lens-family.md](lens-family.md) (when present) or the ThreadLens [API docs](https://github.com/theaussiepom/threadlens/blob/main/docs/api.md).

## Decision-only diagnostic payloads (contract v2)

Current public device, network, Dashboard, and incident-reference payloads are
**decision-led**. They expose a required compact `decision` badge (`DecisionStatus`,
`DecisionPriority`, `headline_code`, coverage labels) and aggregate
`DecisionCountSummary` where appropriate.

Legacy Health/Lens presentation fields (`lens_bucket*`, public `health` as
diagnostic authority, health-derived Dashboard collections) are **not** part of
the current contract. The internal health classifier and operational
`/api/health` / `/healthz` remain available for evaluation and liveness.

## OpenAPI

OpenAPI docs (`/docs`, `/openapi.json`) are disabled by default in production. Set `ZIGBEELENS_OPENAPI_ENABLED=true` for development.
