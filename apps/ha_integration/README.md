# ZigbeeLens Home Assistant integration

ZigbeeLens connects Home Assistant to **ZigbeeLens Core** — the read-only observability engine for Zigbee2MQTT. This integration is the Home Assistant companion surface: summary entities, a native companion panel, diagnostics, and repairs.

The ZigbeeLens sidebar panel is a polished **native companion panel** — a
status and launcher surface, not the full product UI. The full ZigbeeLens
dashboard is served by Core and opens in a new tab with one obvious button.
This works for normal Docker installs **without a reverse proxy**, and avoids
the browser mixed-content block that occurs when Home Assistant uses HTTPS and
Core uses HTTP.

## What this integration does

- Connects Home Assistant to ZigbeeLens Core over HTTP
- Adds summary sensors and binary sensors for automations
- Registers a native companion panel that can show Core decision priorities when contract v2 is available
- Provides an obvious **Open Full ZigbeeLens dashboard** button (opens Core in a new tab)
- Offers optional **Try Embedded View** for the full Core dashboard when browser mixed-content rules allow (native summary remains the default)
- Exposes redacted diagnostics (including decision-contract availability)
- Creates repairs for Core/collector/configuration issues

## What this integration does not do

- Does **not** collect Zigbee2MQTT data directly
- Does **not** replace ZigbeeLens Core or store main history in Home Assistant
- Does **not** mutate Zigbee devices
- Does **not** publish MQTT device-control commands or Zigbee2MQTT request topics for control
- Does **not** create per-priority or per-Device-Story entities; it does provide
  the documented overall/count decision summary entities
- Does **not** invent Decision Engine wording or aggregate severity colouring
- Does **not** require Lovelace YAML

## Prerequisites

Run ZigbeeLens Core using one of:

- **Docker / Compose** — run the standalone container, e.g. `http://host:8377`
- Another Core deployment with an HTTP(S) origin reachable from Home Assistant

For source-built/local pre-release testing, the Home Assistant add-on runner is
intended to provide the full Core UI through Ingress without HACS. The
generated image-based repository is publication-blocked; only a future
published add-on artifact may provide that packaged route after its publication
gates close. The add-on manifest publishes no direct port, and this repository
does not define a portable HACS-to-add-on backend URL.

## Release status — local/staged integration only

**Public HACS installation is unavailable for this reviewed branch.** The
public `theaussiepom/zigbeelens-hacs` satellite is not synchronized with this
staged package and must not be used to validate the branch. Both materially
different trees currently advertise version `0.1.13`. Synchronization,
version-identity repair, and publication require a separate explicitly
authorized task. Docker/Compose is the current portable Core deployment route.

Custom polling persistence, missing/malformed-version compatibility, exact-v2
Dashboard-shape repair guidance, exact-minimum Home Assistant coverage,
manifest `single_config_entry` metadata, and official HACS/hassfest validation
remain open publication gates. Structural package validation does not close
them.

## Local staged integration testing

Use a clean Home Assistant test instance running **2025.1.0 or newer**. HACS is
not used for this branch test.

Package metadata declares that minimum, but the current test dependency uses
`homeassistant>=2025.1.0` and resolves a newer release. Exact 2025.1.0 plus
current-Home-Assistant matrix coverage remains a HACS publication gate.

1. From the monorepo root, generate and validate the staged package:

   ```bash
   ./scripts/package-hacs-repo.sh
   bash dist/zigbeelens-hacs/scripts/validate-hacs-repo.sh
   ```

2. Run ZigbeeLens Core (see
   [docs/release-test.md](../../docs/release-test.md) for `:edge` pre-release
   testing).
3. Copy `dist/zigbeelens-hacs/custom_components/zigbeelens/` so its contents
   land at
   `<home-assistant-config>/custom_components/zigbeelens/`. On HAOS the
   configuration root is normally `/config`. Copy only the integration
   directory, use a clean destination, and replace an existing copy as one unit
   while Home Assistant is stopped.
4. Perform a full Home Assistant restart.
5. Open **Settings → Devices & services → Add Integration → ZigbeeLens**.

Do not use the public HACS satellite for this test.

Only one ZigbeeLens config entry/Core target is supported. The config flow
rejects a second entry; declarative `single_config_entry` manifest metadata is
not yet present and remains a packaging-alignment gate.

Monorepo staging for maintainers:

```bash
./scripts/package-hacs-repo.sh
```

Output: `dist/zigbeelens-hacs/`. It is a generated validation/install stage,
not a repository to push. Satellite synchronization requires a separate
authorized publication task.

### Core URL and embedded view

The Core URL is the address Home Assistant uses to reach ZigbeeLens Core.

HTTP Core URLs are the normal Docker path and work for the native companion panel, entities, repairs, diagnostics, and **Open Full Dashboard**.

The optional embedded dashboard view usually requires an **HTTPS Core URL** when Home Assistant is served over HTTPS. Change the Core URL through **Reconfigure** — no need to delete and re-add the integration.

See [docs/hacs-embedded-view.md](../../docs/hacs-embedded-view.md) for HTTPS reverse proxy options (Traefik on Beast, Caddy example, etc.).

## Conditional public HACS installation

Public custom-repository installation is a future route only. Before restoring
it, the staged tree must match the intended satellite tree, the package version
must uniquely identify that tree, exact Home Assistant 2025.1.0 plus current
coverage must pass, official HACS and hassfest validation must pass, and
explicit publication authorization must be recorded. Only after those gates
close may operators add the synchronized
`https://github.com/theaussiepom/zigbeelens-hacs` repository in HACS.

## Configure

During setup you will be asked for:

| Option | Default | Description |
|--------|---------|-------------|
| Core URL | `http://localhost:8377` | Address of your ZigbeeLens Core dashboard — replace the default unless Core truly shares Home Assistant's network namespace. It must be reachable **from Home Assistant**. HTTP is fine for the native panel and **Open Full Dashboard**. Use HTTPS for the optional embedded view when Home Assistant uses HTTPS. |
| Core API token | blank | Optional. Same value as Core `security.api_token` when Core protects its API. Stored in Home Assistant config-entry data; sent only as a server-side `Authorization: Bearer` header. |
| Verify SSL | `false` | Verify the Core TLS certificate when enabled. |
| Panel enabled | `true` | Show the ZigbeeLens companion panel in the Home Assistant sidebar. |

Polling currently uses the 60-second default. **Configure** accepts a
15–900-second value, but the current OptionsFlow returns an empty options result
after its intermediate update, so Home Assistant overwrites the chosen interval
and it does not persist. This is an open release blocker; do not rely on custom
polling intervals until a persistence/reload test passes.

Examples: `http://192.168.1.10:8377`, `https://zigbeelens.example.com`

Setup validates public `GET /api/version` (product proof, no Authorization), then protected `GET /api/health` with the bearer when configured.

The Core URL must be an exact HTTP(S) origin with no path, query, fragment, or
embedded credentials.

| Flow | Use for |
|------|---------|
| **Configure** (options) | Panel visibility; polling interval is exposed but has the persistence blocker above |
| **Reconfigure** | Core URL, TLS verification, API token replace/remove |
| **Reauthenticate** | Offered automatically when Core rejects the stored token |

Home Assistant reloads the config entry after these changes. Integration logs
are in Home Assistant's normal logs; use the ZigbeeLens integration/device
diagnostics menu for a redacted diagnostics download.

The API token is never placed in panel JavaScript, websocket data, iframe URLs,
or **Open Full Dashboard**. Standalone browser login exists only when Core has
both `security.api_token` and `security.session_secret`; a bearer-only Core
deliberately leaves the bundled browser UI locked. Protect Home Assistant
administrators and backups accordingly — the token lives in HA config-entry
storage. Diagnostics expose only `api_token_configured` (boolean).

### URL hints

| Deployment | Typical Core URL |
|------------|-------------------|
| Docker on LAN (pre-release) | `http://<docker-host-ip>:8377` |
| Docker Compose same network | `http://zigbeelens:8377` |

Do not use `http://localhost:8377` for source-built/local pre-release add-on
testing or for a future published add-on artifact. Home Assistant Core does not
share the add-on's network namespace, and the source runner exposes port 8377
only to Supervisor Ingress. The generated image-based repository remains
publication-blocked.

## Entities

### Binary sensors

- **ZigbeeLens Active Incident** — on when active incidents exist
- **ZigbeeLens Core Connected** — on when the last coordinator refresh succeeded
- **ZigbeeLens MQTT Collector Connected** — on when Core reports the collector is connected

### Summary sensors (decision contract v2)

Decision-led (new unique IDs — not reused from superseded health entities):

- Overall decision, review-first devices, worth-reviewing devices, coverage warning count

Factual / operational (stable IDs retained where semantics are unchanged):

- Watch devices, unavailable devices, network count, device count, router risks,
  and incident lifecycle state

Superseded health-derived entities (`overall_health`, recently-unstable / weak-link /
stale / low-battery / unknown counts) are no longer registered. Remove leftover
unavailable entities from the Home Assistant entity registry manually if needed.

### Per-network sensors

For each configured network:

- `<Network> Decision`
- `<Network> Unavailable Devices`
- `<Network> Router Risks`

Per-network entities are enumerated when the platform sets up. Reload the
integration after adding or renaming Core networks. Entities for removed
networks can remain unavailable in Home Assistant's entity registry until you
remove them manually.

Detailed diagnostics remain in the ZigbeeLens Core dashboard.

## Companion panel

When enabled, **ZigbeeLens** appears in the Home Assistant sidebar. There are two presentation paths:

### Native companion summary (default)

The sidebar opens on the **native companion panel**. HACS negotiates an exact companion decision contract (`decision_contract_version = 2`). When supported and the Dashboard decision payload is valid:

- **What needs attention now** shows up to three Core investigation priorities
- Core priority labels, titles, and summaries are passed through unchanged
- Factual counts include investigation priorities, data coverage warnings, active incidents, networks, devices, and unavailable devices
- Per-network rows show bridge state, device counts, unavailable counts, and priority counts
- Integration health shows Shared decisions / Decision contract / Core compatibility (Compatible, Incompatible, or Unknown)

Decision mode does **not** use the legacy Current finding card or Health badge as decision authority.

### Optional embedded Core view

When browser mixed-content rules allow, **Try Embedded View** can load the full
Core dashboard in the sidebar (Core must allow the Home Assistant origin in
`frame_ancestor_origins`). HTTPS Home Assistant cannot embed HTTP Core; HTTP
Home Assistant may embed HTTPS Core. Use **Back to Summary** to leave the
iframe, or **Open Full ZigbeeLens dashboard** for a new tab. Invalid Core URLs
never become iframe sources.

When the contract is missing, older, newer, or malformed, the panel shows an
**update required / decision contract incompatible** state with safe connection
and Core version facts only — never Health/Lens diagnostic fallback. This is not
an authentication failure and does not trigger reauth. Disconnected Core shows
compatibility **Unknown**, not Compatible.

Current release blocker: the compatibility helper presently returns `true` for
a missing or malformed Core version. The coordinator can therefore project an
unobserved version as Compatible and use it in the shared-decisions gate. Treat
the Unknown tri-state promise as unverified until that path fails closed and
has coordinator/panel coverage.

An exact-v2 contract with missing or malformed Dashboard decision surfaces is
also collapsed into the same `shared_decisions_available: false` value as an
unsupported contract. Repairs then tells the operator the contract version is
unsupported and to upgrade Core, which is false for a payload-shape failure.
This is a second HACS publication blocker.

Always available actions:

- **Open full ZigbeeLens dashboard** (new tab — primary route into full evidence)
- **Try Embedded View** when browser security allows embedding
- **Copy Core URL** and **Reload status**

The integration provides the decision summary and per-network entities listed
above; it does not create a separate entity for each priority or Device Story.
See [docs/hacs.md](../../docs/hacs.md).

The panel and its websocket summary are available to every authenticated Home
Assistant user, not only administrators. They expose the configured Core URL,
network labels, factual counts, and projected priority text. Use this
integration only where every Home Assistant account may see that information.

To enable embedded view when Home Assistant is HTTPS, put Core behind an HTTPS reverse proxy and update the **Core URL**. See **[HACS embedded view — optional HTTPS reverse proxy](../../docs/hacs-embedded-view.md)**.

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Core unreachable | Core URL, standalone Core service running, firewall |
| Panel shows "not responding" | Core URL reachable from Home Assistant; standalone Core service running; click Reload status |
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

## Upgrade or remove

- For a local/staged update, stop Home Assistant, replace
  `<home-assistant-config>/custom_components/zigbeelens` as one unit, and
  perform a full restart.
- To remove it, delete the ZigbeeLens config entry under **Settings → Devices &
  services**, stop Home Assistant, remove the manually installed
  `custom_components/zigbeelens` directory, and restart. Core and its SQLite
  data are unaffected.
- HACS-managed upgrades apply only to a future synchronized, authorized public
  artifact.

## Safety and security

This integration is read-only toward Zigbee control. It never publishes device-control MQTT commands (permit join, remove/reset, bind/unbind, OTA, channel changes, or device `/set`).

The HACS integration is **not** an authentication layer for ZigbeeLens Core. If your Core URL is reachable by users or networks you do not trust, consider firewall rules, network isolation, Home Assistant Ingress, or an authenticated reverse proxy. HTTPS Core URLs support optional embedded view in the browser; **HTTPS is not authentication**.

Some Core API routes modify ZigbeeLens local data only (reports, topology snapshots, HA enrichment). When topology capture is enabled in Core, Core itself may publish only the allowlisted Zigbee2MQTT network-map request used for observation — that is Core topology policy, not an HACS action. See [docs/security.md](../../docs/security.md).
