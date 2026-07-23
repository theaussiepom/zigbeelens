# Architecture

ZigbeeLens is a read-only, decision-led diagnostics and observability stack for
Zigbee2MQTT. Core owns the canonical evidence model, decisions, API, reports,
and bundled UI. Home Assistant paths are optional deployment and companion
layers.

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
│ normalizer → SQLite → evidence → decisions → incidents/reports │
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
| **Core** | MQTT collector, SQLite, evidence/decision services, incident engine, API, reports, bundled UI |
| **UI** | Decision-led React application served by Core in production |
| **HAOS add-on source** | Runner designed to wrap Core+UI with Supervisor options and Ingress; generated repository is not yet publication-ready |
| **Docker** | Standalone Core+UI container with `/config` + `/data` volumes |
| **HACS integration** | HA config flow, summary entities, native companion panel, repairs |
| **MQTT Discovery** | Optional summary HA entities via configured Discovery and ZigbeeLens-owned state topics |
| **Topology** | Optional point-in-time network map enrichment |
| **HA enrichment** | Optional POST of HA device registry for area/name context |

## Decision-led product

ZigbeeLens uses one shared decision contract across Core, UI, reports, HACS,
and MQTT Discovery. The decision-engine documents record the architecture and
migration that produced the current product:

- [decision-engine.md](decision-engine.md) — decision engine charter, ownership rules and guardrails
- [ux-pruning.md](ux-pruning.md) — UX pruning and surface-role contract
- [decision-engine-migration.md](decision-engine-migration.md) — master phases and sub-phases
- [decision-engine-phase-0.md](decision-engine-phase-0.md) — Phase 0 surface, data, compatibility and rollout governance
- [decision-engine-implementation-plan.md](decision-engine-implementation-plan.md) — implementation record and remaining release phases
- [decision-engine-cursor-guardrails.md](decision-engine-cursor-guardrails.md) — historical execution guardrails and remaining release-phase boundaries

Public product surfaces (UI, exact reports v3, HACS, MQTT Discovery) consume the
**decision contract v2** vocabulary. The internal health classifier and
`health_snapshots` storage remain evaluation inputs; they are not a parallel
public diagnostic authority. Operational liveness remains `/api/health` and
`/healthz`.

The primary UI journey is **Overview** → **Mesh / Investigate** or
**Devices** → contextual evidence and reports. **Incidents**, **Reports**, and
**Settings** remain primary destinations. **Networks**, **Timeline**,
**Topology snapshots**, and **How it works** live under **Advanced & support**.
The removed standalone Routers page is only a compatibility redirect.

## Event pipeline

```
MQTT message
    → topic router (collector)
    → payload normalizer
    → normalized events (SQLite)
    → current device/network state
    → health classification (internal evidence/evaluation)
    → incident correlation
    → decision badges / decision summaries (public contract)
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
| Health (internal) | `health_snapshots` — evaluation history; not public diagnostic DTO fields |
| Incidents | `incidents` |
| Reports | `reports` (redacted exact `ReportDetailV3` body inline) |
| Topology | `topology_snapshots`, `topology_nodes`, `topology_links` |
| HA enrichment | `ha_device_enrichment`, `ha_enrichment_status` |

Reports are stored **in SQLite**, already redacted. Migration 014 removed
development-era v1/v2 rows once; current list, detail, and download paths accept
exact `ReportDetailV3` only. See [reports.md](reports.md) and
[backups.md](backups.md).

The browser also stores local presentation state such as Mesh layout positions,
connection-display preferences, and the last accepted Overview visit boundary.
That browser-local state is not network evidence and is not included in Core
reports.

### Storage maintenance ownership

Core owns SQLite lifecycle end-to-end:

- **Migrations** — Core startup only (maintenance CLI never migrates)
- **Integrity gates** — startup `quick_check` + `foreign_key_check` before destructive work
- **Retention** — startup cycle plus periodic scheduler (`storage.maintenance_interval_hours`); telemetry vs resolved-incident vs report cutoffs are separate
- **Active topology captures** — in-memory pending snapshots are excluded from periodic maintenance; abandoned persisted pending rows are terminalized safely
- **No automatic `VACUUM`** — deleted pages become reusable; file size may not shrink
- **CLI** — `storage check` / `maintenance --dry-run` are non-mutating; `--apply` runs the same executor without migrations
- **SSE invalidation** after successful deletes/updates: `storage_maintenance_completed`, plus `incidents_updated` / `reports_updated` / `timeline_updated` / `topology_updated` when those categories change

Settings shows policy and last-maintenance facts only — no UI purge/vacuum/backup controls.

Identity: **`network_id` + `ieee_address`**. Friendly names are not globally unique.

## Multi-network

Each configured `networks[]` entry maps to one Zigbee2MQTT `base_topic`. Core subscribes per network and tags all data with `network_id`.

## Safety boundaries

### MQTT collector (enabled by default in live mode)

- Runs when `features.mqtt_collector` is true
- **Subscribe-only collector path** — no publish to Zigbee2MQTT topics
- Ingests bridge state, devices, events, logging, health, device payloads, availability

### MQTT Discovery (optional, off by default)

- Normal publishes use the configured discovery prefix and validated
  ZigbeeLens-owned state roots
- Normal publishes reject `/set`, `/bridge/request/`, configured base topics,
  and wildcards
- The broker last-will registration currently precedes normal validation; keep
  the default state prefix and broker ACLs until that release blocker is fixed

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

The HAOS row describes the source runner's intended architecture. The current
generated add-on repository points at the standalone GHCR entrypoint, which
still generates Ingress configuration but omits optional token-file
installation; `/data` writability and Ingress also remain packaged HAOS smoke
gates. See [release-infra.md](release-infra.md).

## Live updates

- Primary: SSE at `GET /api/events/stream`
- Fallback: polling on dashboard pages when SSE unavailable (reverse proxies)

## Related docs

- [decision-engine.md](decision-engine.md) — decision engine charter
- [ux-pruning.md](ux-pruning.md) — UX pruning contract
- [decision-engine-migration.md](decision-engine-migration.md) — decision-engine roadmap
- [decision-engine-phase-0.md](decision-engine-phase-0.md) — Phase 0 governance
- [decision-engine-implementation-plan.md](decision-engine-implementation-plan.md) — Cursor implementation plan
- [decision-engine-cursor-guardrails.md](decision-engine-cursor-guardrails.md) — Cursor model and phase guardrails
- [development.md](development.md) — local dev
- [docker.md](docker.md) — standalone container
- [addon-dev.md](addon-dev.md) — HAOS add-on
- [hacs.md](hacs.md) — HA integration
- [mqtt-discovery.md](mqtt-discovery.md)
- [topology.md](topology.md)
