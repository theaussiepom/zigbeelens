# Contributing to ZigbeeLens

Thank you for helping improve ZigbeeLens. This project prioritizes **safety**, **evidence-based diagnostics**, and **maintainability**.

## Before you start

Read:

- [README.md](README.md) — product scope and safety promises
- [docs/architecture.md](docs/architecture.md) — system design
- [docs/configuration.md](docs/configuration.md) — canonical configuration reference
- [docs/safety-audit.md](docs/safety-audit.md) — non-negotiable guardrails

**Do not add Zigbee mutation, permit join, device removal, OTA, or root-cause claims.**

## Development setup

Install Node.js, pnpm, Python 3.11+, and `uv`, then:

```bash
git clone https://github.com/theaussiepom/zigbeelens.git
cd zigbeelens
pnpm install
cd apps/core
uv sync --extra dev
cd ../..
pnpm --filter @zigbeelens/shared build
export ZIGBEELENS_CONFIG=config/config.yaml
./scripts/dev.sh
```

See [docs/development.md](docs/development.md) for mock vs live mode and MQTT testing.

## Running tests

```bash
# Backend
cd apps/core
uv run pytest -q
uv run pytest -q tests/performance
uv run ruff check src tests
cd ../..

# UI
pnpm --filter @zigbeelens/shared test
pnpm --filter @zigbeelens/shared build
pnpm --filter @zigbeelens/ui test
pnpm --filter @zigbeelens/ui typecheck
pnpm --filter @zigbeelens/ui lint
pnpm --filter @zigbeelens/ui build

# Documentation and cross-surface contracts
./scripts/validate-docs.sh
./scripts/validate-contracts.sh

# HA integration
./scripts/validate-ha-integration.sh

# Add-on packaging
./scripts/validate-addon.sh

# Docker Compose examples
./scripts/validate-compose.sh

# Smoke (quick sanity)
./scripts/smoke-core.sh
```

## Coding standards

### Python (Core)

- Format/lint with **ruff** (`ruff check apps/core/src apps/core/tests`)
- Keep API handlers thin — logic belongs in services
- Use `network_id` + `ieee_address` for device identity
- Prefer evidence/confidence/limitations language in diagnostics

### TypeScript (UI)

- Match existing Tailwind and component patterns in `apps/ui/src/components/`
- Badges must include text labels, not colour alone
- Empty states should be calm and actionable
- No repair/reset/permit-join controls in the UI

### Home Assistant integration

- Read-only bridge to Core — no MQTT collection in the integration
- Diagnostics must be redacted

## Safety guardrails

When changing MQTT-related code, verify:

| Component | Rule |
|-----------|------|
| Collector | The collector path subscribes only; it does not publish |
| MQTT Discovery | Normal publishes must pass topic validation; preserve the documented release blocker until broker last-will registration is validated too |
| Topology | Publish only `{base_topic}/bridge/request/networkmap`; the default delayed startup scan is bounded, while manual capture is feature-gated and confirmed |
| Reports | Redact before storage and download |

Add or update tests in:

- `apps/core/tests/test_mqtt_discovery.py`
- `apps/core/tests/test_topology.py`
- `apps/core/tests/test_safety_guardrails.py`

## Adding diagnostic rules

1. Implement classification in `apps/core/src/zigbeelens/diagnostics/`
2. Include evidence, confidence, and limitations in output models
3. Add a mock scenario or extend an existing one for regression
4. Update docs if user-visible behaviour changes

## Adding report fields safely

1. Add fields to report assembly in `services/reports.py`
2. Register sensitive paths in `services/report_redaction.py`
3. Test all three profiles: `standard`, `public_safe`, `strict`
4. Document in [docs/reports.md](docs/reports.md)

## Adding MQTT topics safely

- **Collector:** subscribe patterns only — review `mqtt/topics.py`
- **Discovery:** validate normal publishes with `mqtt_discovery/topics.py`; also
  close or preserve the safety-audit blocker for broker last-will registration
- **Topology:** validate with `topology/topics.py` — single allowlisted request topic; preserve startup/manual capture gates

Never publish to `{base_topic}/set`, `{base_topic}/bridge/request/*` (except networkmap), or wildcards on Zigbee2MQTT topics.

## Database migrations

1. Add numbered SQL file: `apps/core/src/zigbeelens/db/migrations/NNN_description.sql`
2. Migrations must be idempotent (`IF NOT EXISTS`, etc.)
3. Update `apps/core/tests/test_migrations.py` expected version
4. Document backup impact in [docs/upgrades.md](docs/upgrades.md)

## Pull requests

Use the PR template checklist. Ensure:

- Tests pass
- Docs updated for user-visible changes
- No unsafe MQTT publish paths introduced
- Version bump only when releasing (see [docs/release.md](docs/release.md))

## Questions

Open an [issue](https://github.com/theaussiepom/zigbeelens/issues) for design
questions before large changes.
