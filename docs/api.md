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

All other public routes under `/api/` are also mounted at `/api/v1/` (devices, incidents, networks, topology, enrichment, config status, version, scenarios).

## Authentication

ZigbeeLens Core currently enforces only an optional mutation-route API-key guard. Read routes and SSE remain open. Run on a trusted network or place access control in front of the HTTP service until broader auth lands. See [security.md](security.md).

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

## Home Assistant integration

The HACS integration currently uses legacy `/api/health`, `/api/dashboard`, and related routes. This remains supported. New HA-side code may adopt `/api/v1` when convenient.

See [hacs.md](hacs.md) and [hacs-embedded-view.md](hacs-embedded-view.md).

## Lens family alignment

ThreadLens uses the same `/api/v1` prefix pattern. Shared conventions: [lens-family.md](lens-family.md) (when present) or the ThreadLens [API docs](https://github.com/theaussiepom/threadlens/blob/main/docs/api.md).

## Lens health buckets (presentation layer)

Device entries in dashboard, device detail, and incident payloads include **Lens family** presentation fields:

| Field | Description |
|-------|-------------|
| `lens_bucket` | Shared high-level bucket (`healthy`, `recently_unstable`, `needs_attention`, `unavailable`, `diagnostics_limited`, `informational`, `unknown`) |
| `lens_bucket_label` | Human-readable bucket label |
| `lens_bucket_reason` | Primary reason for the bucket |
| `lens_reasons` | Additional mapped reasons from existing Zigbee health flags |

`lens_bucket` is a **presentation-layer** classification shared across Lens tools. It does **not** replace Zigbee-specific `health.primary`, `health.flags`, or domain reason codes — those remain the source of diagnostic detail.

Mapping uses existing health engine output only; it does not change classification rules.

## OpenAPI

OpenAPI docs (`/docs`, `/openapi.json`) are disabled by default in production. Set `ZIGBEELENS_OPENAPI_ENABLED=true` for development.
