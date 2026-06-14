# ZigbeeLens Home Assistant integration

ZigbeeLens connects Home Assistant to **ZigbeeLens Core** — the read-only observability engine for Zigbee2MQTT. This integration is the Home Assistant control surface: summary entities, sidebar access, diagnostics, and repairs.

## What this integration does

- Connects Home Assistant to ZigbeeLens Core over HTTP
- Adds summary sensors and binary sensors for automations
- Registers a sidebar panel that opens the Core UI
- Exposes redacted diagnostics
- Creates repairs for Core/collector/configuration issues

## What this integration does not do

- Does **not** collect Zigbee2MQTT data directly
- Does **not** replace ZigbeeLens Core or store main history in Home Assistant
- Does **not** mutate Zigbee devices
- Does **not** publish MQTT commands or request topics
- Does **not** require Lovelace YAML

## Prerequisites

Run ZigbeeLens Core using one of:

- **Home Assistant OS add-on** — install and start the ZigbeeLens add-on
- **Docker / Compose** — run the standalone container, e.g. `http://host:8377`

## Install via HACS

Published repository: **https://github.com/theaussiepom/zigbeelens-hacs**

1. Run ZigbeeLens Core (see [docs/release-test.md](../../docs/release-test.md) for `:edge` pre-release testing).
2. **HACS → Integrations → Custom repositories** → add the URL above (Category: Integration).
3. Install **ZigbeeLens** and restart Home Assistant if prompted.
4. **Settings → Devices & services → Add Integration → ZigbeeLens**.

Monorepo packaging for maintainers:

```bash
./scripts/package-hacs-repo.sh
```

Output: `dist/zigbeelens-hacs/` (push to the HACS repo).

## Configure

During setup you will be asked for:

| Option | Description |
|--------|-------------|
| Core URL | Base URL for Core — must be reachable **from Home Assistant** (see [release-test.md](../../docs/release-test.md)) |
| Verify SSL | Enable TLS certificate verification |
| Panel enabled | Show ZigbeeLens in the Home Assistant sidebar |
| Polling interval | How often summary entities refresh (default 60s) |

The config flow validates connectivity with `GET /api/health`.

### URL hints

| Deployment | Typical Core URL |
|------------|-------------------|
| Docker on LAN (pre-release) | `http://<docker-host-ip>:8377` |
| Docker Compose same network | `http://zigbeelens:8377` |
| HAOS add-on (same namespace) | `http://localhost:8377` |

## Entities

### Binary sensors

- **ZigbeeLens Active Incident** — on when active incidents exist
- **ZigbeeLens Core Connected** — on when the last coordinator refresh succeeded
- **ZigbeeLens MQTT Collector Connected** — on when Core reports the collector is connected

### Summary sensors

- Overall health, incident state, unavailable devices, recently unstable devices
- Router risks, stale devices, weak link devices, low battery devices, unknown devices
- Network count, device count

### Per-network sensors

For each configured network:

- `<Network> Health`
- `<Network> Unavailable Devices`
- `<Network> Router Risks`

Detailed diagnostics remain in the ZigbeeLens Core dashboard.

## Sidebar panel

When enabled, **ZigbeeLens** appears in the sidebar and embeds the Core UI via iframe.

**If the panel is blank:**

- Update the HACS integration to the latest release (older builds registered the wrong panel component).
- If Home Assistant uses **HTTPS** and Core uses **HTTP**, HA blocks the iframe. Open Core directly in a browser tab (e.g. `http://<docker-host-ip>:8377`), or serve Core over HTTPS / use HTTP for HA on your LAN during testing.

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Core unreachable | Core URL, container/add-on running, firewall |
| Panel not loading | Panel enabled in options; try opening Core URL directly |
| Add-on vs Docker URL | Use a URL reachable from Home Assistant Core, not your browser only |
| Collector disconnected | MQTT settings in Core; broker reachable from Core |
| No devices showing | Networks configured in Core; MQTT traffic observed |
| Mock mode active | Core running with mock scenarios — expected for demos, not production |
| Version mismatch | Upgrade Core and integration together |

## Development

```bash
./scripts/validate-ha-integration.sh
```

Tests live in `apps/ha_integration/tests/`.

## Safety

This integration is read-only. It never publishes MQTT, sends Zigbee2MQTT request topics, or mutates Zigbee state.
