# HTTP API

ZigbeeLens Core exposes a JSON API for the dashboard, Home Assistant
integration, and external tools. Zigbee device behaviour is read-only.
Authenticated mutations manage ZigbeeLens-local reports, browser sessions,
topology capture records, and Home Assistant enrichment. A topology capture
also emits the separately allowlisted diagnostic network-map request described
in [topology.md](topology.md); it is not a device-control write.

## API prefix

**`/api/v1` is the preferred prefix for new integrations.**

Existing `/api/*` routes remain available for backward compatibility. Both prefixes serve the same handlers.

| Preferred (v1) | Legacy alias |
|----------------|--------------|
| `GET /api/v1/health` | `GET /api/health` |
| `GET /api/v1/dashboard` | `GET /api/dashboard` |
| `GET /api/v1/capabilities` | `GET /api/capabilities` |
| `GET /api/v1/status` | `GET /api/status` |
| `GET /api/v1/events/stream` | `GET /api/events/stream` |
| `GET /api/v1/reports` | `GET /api/reports` |
| `GET /api/v1/storage/status` | `GET /api/storage/status` |

All other API routes under `/api/` are also mounted at `/api/v1/` (devices,
incidents, networks, topology, enrichment, config status, version, scenarios).

## Authentication

The same authentication policy applies under both API prefixes.

| Method | Contract |
|--------|----------|
| Trusted local | `security.mode: local` with no API token admits protected reads and mutations as `trusted_local`. Session bootstrap is not available. |
| Bearer | `Authorization: Bearer <token>`. A presented Authorization header always takes precedence; malformed or wrong bearer credentials fail with `401` and do not fall back to another method. Bearer mutations do not need Origin or CSRF. |
| Browser session | Configure both `security.api_token` and `security.session_secret`, then exchange the bearer at `POST /api/v1/auth/session`. Reads accept the signed `zigbeelens_session` cookie. Cookie-authenticated `POST`, `PUT`, `PATCH`, and `DELETE` requests require one allowed `Origin` and one `X-ZigbeeLens-CSRF-Token`. |
| Home Assistant ingress | In `home_assistant_ingress` mode, Core accepts a validated Supervisor user ID only from an exact configured ASGI peer. Ingress-authenticated mutations do not use Core session CSRF. Client-supplied `X-Remote-User-*` headers are not credentials. |

`GET /api/v1/auth/session` is public and returns only session posture plus, for
an authenticated Core browser session, its expiry and a CSRF token. It never
returns a session ID, cookie value, API token, or Home Assistant user ID.
`POST /api/v1/auth/session` is bearer-bootstrap only. `DELETE
/api/v1/auth/session` is a mutation, so a browser session must send its allowed
Origin and CSRF token when signing out.

The always-public machine endpoints are `GET /healthz`, `GET /api/version`, and
`GET /api/v1/version`; the two session-status aliases are also public. In
Home Assistant proxy-only posture, direct access to the static UI is denied even
though those probes remain available.

See [security.md](security.md) for cookie attributes, origin rules, ingress
trust, and configuration.

### Error responses

Explicit HTTP errors use FastAPI's JSON shape:

```json
{
  "detail": "Report not found"
}
```

Request-schema validation errors use `detail` as an array of validation
entries. Authentication failures use the same non-revealing `401` detail for
missing and invalid credentials and include `WWW-Authenticate: Bearer`.
Session Origin and CSRF failures are `403`; trying to create a browser session
when sessions are not configured is `409`.

Report target existence is not a request-validation error today: an unknown
network, incident, or unambiguous device target produces an exact-v3 report
with an empty target plan. Ambiguous device identity is `422`. Verify a target
with its read endpoint first when the caller requires `404` semantics.

## Core endpoints

### Health

`GET /api/v1/health` — service health, database, collector summary, optional feature status (MQTT discovery, topology, HA enrichment). Collector errors are redacted.

### Capabilities

`GET /api/v1/capabilities` — stable feature and contract flags for integrations
(no secrets). A live configuration can return:

```json
{
  "product": "zigbeelens",
  "version": "0.1.14",
  "decision_contract_version": 2,
  "home_assistant_enrichment_contract_version": 1,
  "capabilities": {
    "dashboard": true,
    "sse": true,
    "reports": true,
    "mqtt_discovery": false,
    "home_assistant_enrichment": true,
    "topology": true,
    "mock_scenarios": true,
    "read_only_observability": true,
    "mqtt_collector": true,
    "shared_decisions": true,
    "decision_only_diagnostic_payloads": true,
    "legacy_health_lens_payloads": false,
    "companion_decision_summary": true,
    "report_contract_v3": true,
    "decision_mqtt_summary": true,
    "bearer_authentication": true,
    "browser_session_authentication": true,
    "csrf_protection": true,
    "exact_cors_allowlist": true,
    "content_security_policy": true,
    "frame_ancestor_allowlist": true,
    "browser_origin_validation": true,
    "home_assistant_ingress_identity": true,
    "trusted_ingress_peer_enforcement": true,
    "ingress_browser_authentication": true,
    "retention_policy_v2": true,
    "periodic_storage_maintenance": true,
    "online_sqlite_backup_cli": true,
    "storage_integrity_checks": true
  },
  "decision_surfaces": {
    "dashboard_decision_summary": true,
    "network_decision_badges": true,
    "device_decision_badges": true,
    "device_story": true,
    "incident_device_decisions": true,
    "report_decision_sections": true,
    "dashboard_investigation_priorities": true,
    "dashboard_data_coverage_warnings": true,
    "report_device_stories": true
  }
}
```

`mqtt_discovery` reflects `features.mqtt_discovery`; effective Discovery still
requires its separate `mqtt_discovery.enabled` flag. `topology` reflects
`topology.enabled`. `mqtt_collector` reflects whether the collector is enabled
for the current live/mock and MQTT configuration. These are capability/config
facts, not broker connection success.

### Home Assistant enrichment

`POST /api/v1/enrichment/homeassistant` (legacy alias:
`POST /api/enrichment/homeassistant`) accepts one complete, strict contract-v1
snapshot. The exact top-level shape is:

```json
{
  "home_assistant_enrichment_contract_version": 1,
  "devices": [
    {
      "network_id": "home",
      "ieee_address": "0x00124b0024abcd01",
      "ha_device_id": "ha-device-registry-id",
      "ha_device_name": "Kitchen lamp",
      "area_id": "kitchen",
      "area_name": "Kitchen",
      "entity_id": "light.kitchen_lamp"
    }
  ]
}
```

Every row requires `network_id`, an exact normalized 64-bit Zigbee IEEE, and
the HA device-registry ID. Name, area ID/name, and one deterministic
representative entity ID are nullable metadata. Unknown fields, duplicate exact
identities, one HA device/representative entity assigned to multiple Core
identities, malformed strings, and oversized snapshots are rejected before
storage.

Core matches only the final exact `(network_id, ieee_address)` pair. HA user
names are never identity. An accepted request atomically replaces enrichment
rows and status; a complete empty `devices` list clears the snapshot. Request
validation, authentication, matching, or persistence/transaction failure before
commit leaves the previous accepted snapshot untouched. The response reports exact
`submitted`, `matched`, `unmatched`, `ambiguous`, `stored`, `last_push_at`, and
contract-version facts.

`DELETE /api/v1/enrichment/homeassistant` is the exact explicit clear route.
The HACS client uses it only during explicit config-entry removal. Core device
payloads preserve `friendly_name` and add nullable `home_assistant_name` and
`home_assistant_area_name` fields (`ha_area` remains a compatibility alias).
HA metadata in reports follows the selected redaction profile.

After a POST replacement or DELETE clear commits, Core independently attempts
exactly one `home_assistant_enrichment_updated` SSE event and exactly one
current Dashboard rebuild. A post-commit event or Dashboard failure is logged
with fixed categorical context only, does not block the other attempt, and
cannot change the accepted HTTP response or committed data. On the normal
successful path, the event is an identity-free invalidation signal:

```json
{
  "type": "home_assistant_enrichment_updated",
  "home_assistant_enrichment_contract_version": 1,
  "submitted": 1,
  "matched": 1,
  "unmatched": 0,
  "ambiguous": 0,
  "stored": 1
}
```

DELETE emits the same shape with all five counts set to zero. The payload never
contains an IEEE, HA device/entity ID, name, area, token, or URL. Authentication,
validation, matching, and persistence/transaction failures before commit emit
no event and schedule no Dashboard rebuild. These rules are identical through
`/api` and `/api/v1`.

The accompanying successful `dashboard_updated` event includes the categorical
cause `home_assistant_enrichment_updated`. Resources whose payload cannot change
from HA enrichment use that identity-free cause to ignore the companion.
Enrichment-owning resources accept both event types because a browser may miss
the preceding exact event. The normal immediate pair is debounced into one
logical refresh; a delayed companion can produce a second at-least-once refresh
to preserve convergence. An ordinary or coalesced unattributed Dashboard update
remains generic and is not suppressed.

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

`GET /api/v1/events/stream` — Server-Sent Events stream (heartbeat, dashboard
updates, collector status, and post-commit enrichment invalidation).

### Reports

- `GET /api/v1/reports/preview` — return an exact `ReportDetailV3` without storing it
- `POST /api/v1/reports` — generate and store; returns `ReportSummary`
- `GET /api/v1/reports` — list `ReportSummary` rows for valid exact-v3 reports
- `GET /api/v1/reports/{report_id}` — return the stored exact `ReportDetailV3`
- `GET /api/v1/reports/{report_id}/download` — download the format selected when the report was created
- `DELETE /api/v1/reports/{report_id}` — delete the local stored row; returns `{"deleted": true}`

JSON, YAML, and Markdown downloads use `application/json`,
`application/x-yaml`, and `text/markdown`, respectively. A malformed or non-v3
stored row is omitted from the list and returns `404` from detail/download; it
is not interpreted as a legacy report.

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

The HACS integration reads legacy `/api/health`, `/api/dashboard`,
`/api/config/status`, and `/api/capabilities` through shared supported handlers,
with an optional server-side `Authorization: Bearer` header (never in URLs).
Enrichment uses preferred `/api/v1/devices` inventory plus only the exact v1
snapshot POST and optional explicit-removal DELETE described above. It does not
expose or use a generic Core mutation method.

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
