# ZigbeeLens Home Assistant integration

ZigbeeLens connects Home Assistant to **ZigbeeLens Core** — the read-only observability engine for Zigbee2MQTT. This integration is the Home Assistant companion surface: summary entities, a native companion panel, diagnostics, and repairs.

The HACS sidebar panel is a polished **native companion panel** — a status and launcher surface, not the full product UI. The full ZigbeeLens dashboard is served by Core and opens in a new tab with one obvious button. This works for normal Docker installs **without a reverse proxy**, and avoids the browser mixed-content block that occurs when Home Assistant uses HTTPS and Core uses HTTP.

## What this integration does

- Connects Home Assistant to ZigbeeLens Core over HTTP
- Adds summary sensors and binary sensors for automations
- Registers a native companion panel that can show Core decision priorities when contract v1 is available
- Provides an obvious **Open Full ZigbeeLens dashboard** button (opens Core in a new tab)
- Offers optional **Try Embedded View** for the full Core dashboard when schemes match (native summary remains the default)
- Exposes redacted diagnostics (including decision-contract availability)
- Creates repairs for Core/collector/configuration issues

## What this integration does not do

- Does **not** collect Zigbee2MQTT data directly
- Does **not** replace ZigbeeLens Core or store main history in Home Assistant
- Does **not** mutate Zigbee devices
- Does **not** publish MQTT device-control commands or Zigbee2MQTT request topics for control
- Does **not** create decision entities for investigation priorities or Device Stories
- Does **not** invent Decision Engine wording or aggregate severity colouring
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

### Core URL and embedded view

The Core URL is the address Home Assistant uses to reach ZigbeeLens Core.

HTTP Core URLs are the normal Docker path and work for the native companion panel, entities, repairs, diagnostics, and **Open Full Dashboard**.

The optional embedded dashboard view usually requires an **HTTPS Core URL** when Home Assistant is served over HTTPS. Change the Core URL through **Reconfigure** — no need to delete and re-add the integration.

See [docs/hacs-embedded-view.md](../../docs/hacs-embedded-view.md) for HTTPS reverse proxy options (Traefik on Beast, Caddy example, etc.).

## Configure

During setup you will be asked for:

| Option | Description |
|--------|-------------|
| Core URL | Address of your ZigbeeLens Core dashboard — must be reachable **from Home Assistant**. HTTP is fine for the native panel and **Open Full Dashboard**. Use HTTPS if you want the optional embedded dashboard view inside Home Assistant. |
| Core API token | Optional. Same value as Core `security.api_token` when Core protects its API. Leave blank for trusted-open Core. Stored in Home Assistant config-entry data; sent only as a server-side `Authorization: Bearer` header. |
| Verify SSL | Enable TLS certificate verification |
| Panel enabled | Show the ZigbeeLens companion panel in the Home Assistant sidebar |

Polling interval defaults to 60s and is adjusted later under **Configure** (options).

Examples: `http://192.168.1.10:8377`, `https://zigbeelens.example.com`

Setup validates public `GET /api/version` (product proof, no Authorization), then protected `GET /api/health` with the bearer when configured.

| Flow | Use for |
|------|---------|
| **Configure** (options) | Panel visibility and polling interval |
| **Reconfigure** | Core URL, TLS verification, API token replace/remove |
| **Reauthenticate** | Offered automatically when Core rejects the stored token |

The API token is never placed in panel JavaScript, websocket data, iframe URLs, or **Open Full Dashboard**. Those browser paths use standalone UI session login when Core is protected. Protect Home Assistant administrators and backups accordingly — the token lives in HA config-entry storage. Diagnostics expose only `api_token_configured` (boolean).

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

## Companion panel

When enabled, **ZigbeeLens** appears in the Home Assistant sidebar. There are two presentation paths:

### Native companion summary (default)

The sidebar opens on the **native companion panel**. HACS negotiates an exact companion decision contract (`decision_contract_version = 1`). When supported and the Dashboard decision payload is valid:

- **What needs attention now** shows up to three Core investigation priorities
- Core priority labels, titles, and summaries are passed through unchanged
- Factual counts include investigation priorities, data coverage warnings, active incidents, networks, devices, and unavailable devices
- Per-network rows show bridge state, device counts, unavailable counts, and priority counts
- Integration health shows Shared decisions / Decision contract / Core compatibility (Compatible, Incompatible, or Unknown)

Decision mode does **not** use the legacy Current finding card or Health badge as decision authority.

### Optional embedded Core view

When Home Assistant and Core use the same protocol, **Try Embedded View** can load the full Core dashboard in the sidebar (Core must allow the Home Assistant origin in `frame_ancestor_origins`). Use **Back to Summary** to leave the iframe, or **Open Full ZigbeeLens dashboard** for a new tab. Mixed-content and invalid Core URLs never become iframe sources.

When the contract is missing, unsupported, or the Dashboard surfaces are malformed, the panel falls back to a factual connection/network/incident summary without inventing diagnoses. Disconnected Core shows compatibility **Unknown**, not Compatible.

Always available actions:

- **Open full ZigbeeLens dashboard** (new tab — primary route into full evidence)
- **Try Embedded View** when browser security allows embedding
- **Copy Core URL** and **Reload status**

Phase 5E adds no new Home Assistant entities for decisions. See [docs/hacs.md](../../docs/hacs.md).

To enable embedded view when Home Assistant is HTTPS, put Core behind an HTTPS reverse proxy and update the **Core URL**. See **[HACS embedded view — optional HTTPS reverse proxy](../../docs/hacs-embedded-view.md)**.

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Core unreachable | Core URL, container/add-on running, firewall |
| Panel shows "not responding" | Core URL reachable from Home Assistant; container/add-on running; click Reload status |
| Open Dashboard button | Opens Core in a new tab; if the tab fails, Core itself is unreachable from your browser/LAN |
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

## Safety and security

This integration is read-only toward Zigbee control. It never publishes device-control MQTT commands (permit join, remove/reset, bind/unbind, OTA, channel changes, or device `/set`).

The HACS integration is **not** an authentication layer for ZigbeeLens Core. If your Core URL is reachable by users or networks you do not trust, consider firewall rules, network isolation, Home Assistant Ingress, or an authenticated reverse proxy. HTTPS Core URLs support optional embedded view in the browser; **HTTPS is not authentication**.

Some Core API routes modify ZigbeeLens local data only (reports, topology snapshots, HA enrichment). When topology capture is enabled in Core, Core itself may publish only the allowlisted Zigbee2MQTT network-map request used for observation — that is Core topology policy, not an HACS action. See [docs/security.md](../../docs/security.md).
