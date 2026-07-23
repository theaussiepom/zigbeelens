# ZigbeeLens Core

FastAPI diagnostic service for Zigbee2MQTT observability. Core owns MQTT
collection, SQLite persistence, deterministic diagnostics, contextual report
generation, and the HTTP/SSE API consumed by the web UI and optional Home
Assistant companion. The API does not control Zigbee devices; some routes
mutate ZigbeeLens-local reports, topology snapshots, enrichment, or browser
session state.

Core does not mutate Zigbee devices. Its narrowly bounded publishers are:

- MQTT Discovery state/config topics below the configured discovery and
  ZigbeeLens prefixes. Normal publishes are topic-validated; the current
  broker-last-will registration ordering remains a release blocker documented
  in the safety audit.
- The allowlisted Zigbee2MQTT
  `{base_topic}/bridge/request/networkmap` topology request. A delayed startup
  scan is enabled by default; manual capture requires its explicit gate and
  confirmation.

Start with the repository [README](../../README.md), then use:

- [Configuration reference](../../docs/configuration.md)
- [API contract](../../docs/api.md)
- [Architecture](../../docs/architecture.md)
- [Safety audit](../../docs/safety-audit.md)
- [Development guide](../../docs/development.md)

For local development:

```bash
cd apps/core
uv sync --extra dev
uv run pytest -q
uv run ruff check src tests
```

Run Core from the repository root so relative configuration and storage paths
resolve predictably:

```bash
export ZIGBEELENS_CONFIG=config/config.yaml
apps/core/.venv/bin/python -m zigbeelens
```
