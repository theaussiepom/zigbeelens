# Architecture

ZigbeeLens is a read-only observability stack for Zigbee2MQTT. Core owns the canonical dashboard and data model. Home Assistant paths are optional access and enrichment layers.

## Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        Zigbee2MQTT                               │
│              (bridge state, devices, payloads)                   │
└────────────────────────────┬────────────────────────────────────┘
                             │ MQTT subscribe (collector)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ZigbeeLens Core                              │
│  normalizer → SQLite → health → incidents → dashboard/reports   │
└───┬──────────────┬──────────────┬──────────────┬──────────────────┘
    │              │              │              │
    ▼              ▼              ▼              ▼
 Bundled UI    MQTT Discovery   Topology      HA enrichment
 (React)       (optional)       (optional)    API (optional)
    │
    ▼
 HACS integration ──HTTP read-only──► Core
 (entities, native companion panel, diagnostics)
```

| Component | Role |
|-----------|------|
| **Core** | MQTT collector, SQLite, health/incident engines, API, bundled UI |
| **UI** | React dashboard served by Core in production |
| **HAOS add-on** | Wraps Core+UI with Supervisor options and Ingress |
| **Docker** | Standalone Core+UI container with `/config` + `/data` volumes |
| **HACS integration** | HA config flow, summary entities, native companion panel, repairs |
| **MQTT Discovery** | Optional summary HA entities via `homeassistant/` topics |
| **Topology** | Optional point-in-time network map enrichment |
| **HA enrichment** | Optional POST of HA device registry for area/name context |

## Decision engine programme

ZigbeeLens is evolving from a dashboard/graph product into a shared decision-engine investigation product. The decision-engine docs define the architecture contract for that work:

- [decision-engine.md](decision-engine.md) — decision engine charter, ownership rules and guardrails
- [ux-pruning.md](ux-pruning.md) — UX pruning and surface-role contract
- [decision-engine-migration.md](decision-engine-migration.md) — master phases and sub-phases
- [decision-engine-phase-0.md](decision-engine-phase-0.md) — Phase 0 surface, data, compatibility and rollout governance
- [decision-engine-implementation-plan.md](decision-engine-implementation-plan.md) — Cursor-ready implementation plan for the remaining phases

These docs do not change runtime behaviour. They define how future refactors and intelligence features must stay evidence-first, read-only, action-led and consistent across UI, reports and companion surfaces.

## Event pipeline

```
MQTT message
    → topic router (collector)
    → payload normalizer
    → normalized events (SQLite)
    → current device/network state
    → health classification
    → incident correlation
    → dashboard payload / SSE events
    → optional MQTT Discovery update
    → optional report generation (redacted)
```

Topology responses (`bridge/response/networkmap`) are intercepted before the normal event pipeline when topology is enabled.

## Storage model

SQLite database (default `data/zigbeelens.sqlite`):

| Area | Tables (examples) |
|------|-------------------|
| Networks & devices | `networks`, `devices`, `device_snapshots` |
| Telemetry | `events`, `metric_samples`, `availability_changes` |
| Health | `health_snapshots` |
| Incidents | `incidents` |
| Reports | `reports` (JSON body inline) |
| Topology | `topology_snapshots`, `topology_nodes`, `topology_links` |
| HA enrichment | `ha_device_enrichment`, `ha_enrichment_status` |

Reports are stored **in SQLite**, already redacted. See [backups.md](backups.md).

Identity: **`network_id` + `ieee_address`**. Friendly names are not globally unique.

## Multi-network

Each configured `networks[]` entry maps to one Zigbee2MQTT `base_topic`. Core subscribes per network and tags all data with `network_id`.

## Safety boundaries

### MQTT collector (always on in live mode)

- **Subscribe-only** — no publish to Zigbee2MQTT topics
- Ingests bridge state, devices, events, logging, health, device payloads, availability

### MQTT Discovery (optional, off by default)

- Publishes only `homeassistant/...` discovery configs and `zigbeelens/state/...`
- Rejects `/set`, `/bridge/request/`, configured base topics, wildcards

### Topology (enabled by default)

- Enabled by default with one startup network map scan after MQTT collector and bridge readiness
- After startup, relies on passive MQTT updates; periodic active scans disabled unless configured
- Manual capture requires explicit UI/API confirmation
- Single allowlisted publish: `{base_topic}/bridge/request/networkmap`

### Reports

- Assembled from local state, redacted before storage and download
- No raw MQTT secrets in stored reports

### HACS integration

- HTTP read-only to Core
- Does not collect MQTT or mutate Zigbee

Full audit: [safety-audit.md](safety-audit.md)

## Deployment paths

| Path | Entry | Port |
|------|-------|------|
| Dev | `./scripts/dev.sh` | UI 5173, API 8377 |
| Docker | `deploy/docker/docker-compose.example.yaml` | 8377 |
| HAOS add-on | Supervisor Ingress | 8377 internal |
| HACS | Native companion panel (HA websocket summary) + Open Full Dashboard in new tab | via HA |

## Live updates

- Primary: SSE at `GET /api/events/stream`
- Fallback: polling on dashboard pages when SSE unavailable (reverse proxies)

## Related docs

- [decision-engine.md](decision-engine.md) — decision engine charter
- [ux-pruning.md](ux-pruning.md) — UX pruning contract
- [decision-engine-migration.md](decision-engine-migration.md) — decision-engine roadmap
- [decision-engine-phase-0.md](decision-engine-phase-0.md) — Phase 0 governance
- [decision-engine-implementation-plan.md](decision-engine-implementation-plan.md) — Cursor implementation plan
- [development.md](development.md) — local dev
- [docker.md](docker.md) — standalone container
- [addon-dev.md](addon-dev.md) — HAOS add-on
- [hacs.md](hacs.md) — HA integration
- [mqtt-discovery.md](mqtt-discovery.md)
- [topology.md](topology.md)
