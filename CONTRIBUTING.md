# Contributing to ZigbeeLens

Thank you for helping improve ZigbeeLens. This project prioritizes **safety**, **evidence-based diagnostics**, and **maintainability**.

## Before you start

Read:

- [README.md](README.md) — product scope and safety promises
- [docs/architecture.md](docs/architecture.md) — system design
- [docs/safety-audit.md](docs/safety-audit.md) — non-negotiable guardrails

**Do not add Zigbee mutation, permit join, device removal, OTA, or root-cause claims.**

## Development setup

```bash
git clone https://github.com/theaussiepom/zigbeelens.git
cd zigbeelens
pnpm install
python3 -m venv apps/core/.venv
source apps/core/.venv/bin/activate
pip install -e "apps/core[dev]"
pnpm --filter @zigbeelens/shared build
export ZIGBEELENS_CONFIG=config/config.yaml
./scripts/dev.sh
```

See [docs/development.md](docs/development.md) for mock vs live mode and MQTT testing.

## Running tests

```bash
# Backend
source apps/core/.venv/bin/activate
PYTHONPATH=apps/core/src pytest apps/core/tests -q

# UI
pnpm --filter @zigbeelens/ui test
pnpm --filter @zigbeelens/ui typecheck

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
| Collector | Subscribe-only — no publish to Zigbee2MQTT topics |
| MQTT Discovery | Publish only `homeassistant/` and `zigbeelens/` |
| Topology | Only `{base_topic}/bridge/request/networkmap`, feature-gated + confirmed |
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
- **Discovery:** validate with `mqtt_discovery/topics.py` — must pass `validate_publish_topic`
- **Topology:** validate with `topology/topics.py` — single allowlisted request topic

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

Open a [discussion](https://github.com/theaussiepom/zigbeelens/discussions) or issue for design questions before large changes.
