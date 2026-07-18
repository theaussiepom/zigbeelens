# Development

Guide for working on ZigbeeLens locally.

For architecture overview see [architecture.md](architecture.md). For MQTT broker testing see [mqtt-dev.md](mqtt-dev.md).

## Prerequisites

- Node.js 20+
- pnpm 9+ (`corepack enable`)
- Python 3.11+

## First-time setup

```bash
cd zigbeelens
pnpm install
python3 -m venv apps/core/.venv
source apps/core/.venv/bin/activate
pip install -e "apps/core[dev]"
pnpm --filter @zigbeelens/shared build
```

## Configuration

Default config: `config/config.yaml`

Override:

```bash
export ZIGBEELENS_CONFIG=/path/to/config.yaml
```

### Mock mode (default)

```yaml
mode:
  mock: true
  default_scenario: four_devices_same_room_unavailable
```

All 14 diagnostic stories are available via `?scenario=` on API calls and the UI dropdown.

### Live mode

Copy `config/config.live.example.yaml`:

```yaml
mode:
  mock: false
storage:
  path: ./data/zigbeelens.sqlite
mqtt:
  server: mqtt://127.0.0.1:1883
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
```

With live mode and no MQTT data yet, the API returns valid empty/unknown payloads.

## Run Core + UI

```bash
export ZIGBEELENS_CONFIG=config/config.yaml
./scripts/dev.sh
```

Or manually:

```bash
# Terminal 1 — Core (bind comes from AppConfig; source default is 127.0.0.1:8377)
export ZIGBEELENS_CONFIG=config/config.yaml
source apps/core/.venv/bin/activate
PYTHONPATH=apps/core/src python -m zigbeelens --reload

# Terminal 2 — UI
pnpm --filter @zigbeelens/ui dev
```

- UI: http://localhost:5173 (proxies API to localhost:8377)
- API docs: http://localhost:8377/docs (enable with `ZIGBEELENS_OPENAPI_ENABLED=true`)

The Vite `/api` proxy is the preferred local workflow: browser requests stay
same-origin with the UI, which keeps HttpOnly session cookies and
`SameSite=Strict` working without cross-origin CORS setup.

To exercise the standalone login screen locally, configure both
`security.api_token` and `security.session_secret` (or their
`ZIGBEELENS_SECURITY_*` / `*_FILE` equivalents) and restart Core. Do **not** put
the API token in `VITE_*` variables or bake it into frontend assets — the UI
accepts the token only in the password-style unlock field and exchanges it once
for a browser session.

Do not pass a separate `--host`/`--port` that can disagree with `server.host` / `server.port` in config. Optional port compatibility override: `ZIGBEELENS_PORT` (resolved into typed AppConfig).

## Docker dev

Compose development uses `deploy/compose/config.dev.yaml` with an explicit container bind of `0.0.0.0` so the UI service can reach Core. The source/default config remains loopback.

```bash
docker compose -f deploy/compose/docker-compose.dev.yaml up --build
```

## Tests

```bash
source apps/core/.venv/bin/activate
PYTHONPATH=apps/core/src pytest apps/core/tests -q
pnpm --filter @zigbeelens/ui test
pnpm --filter @zigbeelens/ui typecheck
ruff check apps/core/src apps/core/tests
./scripts/validate-ha-integration.sh
./scripts/validate-addon.sh
./scripts/validate-compose.sh
./scripts/smoke-core.sh
```

## Repository layout

```
apps/core/           Python FastAPI service
apps/ui/             React + Vite dashboard
apps/ha_integration/ HACS custom integration
apps/addon/          Home Assistant OS add-on
packages/shared/     TypeScript shared types
deploy/docker/       Production Dockerfile + Compose
deploy/compose/      Dev Compose
scripts/             Build, validate, smoke scripts
docs/                Documentation
```

## Key modules

| Layer | Path |
|-------|------|
| Config | `apps/core/src/zigbeelens/config/` |
| MQTT collector | `apps/core/src/zigbeelens/mqtt/` |
| Health / incidents | `apps/core/src/zigbeelens/diagnostics/` |
| Reports / redaction | `apps/core/src/zigbeelens/services/reports.py`, `report_redaction.py` |
| MQTT Discovery | `apps/core/src/zigbeelens/mqtt_discovery/` |
| Topology | `apps/core/src/zigbeelens/topology/` |
| API | `apps/core/src/zigbeelens/api/routes.py` |

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md).
