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
- Publishes one strict, bounded Home Assistant registry metadata snapshot to
  Core-local enrichment storage

## What this integration does not do

- Does **not** collect Zigbee2MQTT data directly
- Does **not** replace ZigbeeLens Core or store main history in Home Assistant
- Does **not** mutate Zigbee devices
- Does **not** publish MQTT or talk to Zigbee2MQTT
- Does **not** create per-priority or per-Device-Story entities; it does provide
  the documented overall/count decision summary entities
- Does **not** invent Decision Engine wording or aggregate severity colouring
- Does **not** require Lovelace YAML

## Prerequisites

Run ZigbeeLens Core using one of:

- **Docker / Compose** — run the standalone container, e.g. `http://host:8377`
- Another Core deployment with an HTTP(S) origin reachable from Home Assistant

The Home Assistant add-on is deferred and is not part of this HACS release. It
does not define a portable HACS-to-add-on backend URL.

## Release status — pre-release validation only

**General-public HACS installation remains unavailable.** At the
pre-synchronization review, public `theaussiepom/zigbeelens-hacs` `main` was
the prior candidate at commit
`21c24e3355369b94c9ab596cf9fc0591f1282297`, tree
`9e33bcbf919cdc90eee37e6c3f635f6b6292fbc9`, with `SOURCE_COMMIT`
`906527063ad8bd594fbec51f69f6fc72205302dd`, manifest version `0.1.14`, and no
`v0.1.14` tag or release. That historical tree is not the corrected candidate.
Synchronization, Phase 7D installation, and final publication require separate
explicit authorizations. Docker/Compose remains the portable Core deployment
route.

Phase 7C1 and Phase 7C2 are complete and merged. PR #108's evidence merge is
`93fb26617042ed46d8920a7b75a42e3ae9da4d62`; all S1–S9 screenshots retain
immutable runtime capture source
`af04ee906b71de77ee6e0eb5d866c0647d502410`. Phase 7D remains blocked until a
final docs-bearing tree from merged main is synchronized and reviewed exactly,
both exact HA lanes and official HACS/hassfest checks pass remotely, the final
artifact pairing is frozen, and separate explicit Phase 7D authorization is
recorded.

Before release, `SOURCE_COMMIT` plus the generated Git tree identify the exact
candidate; manifest version `0.1.14` is aligned but does not distinguish
candidate trees by itself. General-public installation remains unavailable
until Phase 7D is complete and final release authorization requires the
`v0.1.14` tag and GitHub release to point to that exact reviewed synchronized
tree.

## Local staged integration testing

Use a clean Home Assistant test instance. HACS is not used for this branch
test. The reviewed exact lanes are:

| Lane | Home Assistant | Python |
|------|----------------|--------|
| Minimum | `2025.1.0` | `3.12` |
| Current | `2026.7.3` | `3.14` |

Run them with `bash scripts/test-ha-integration-matrix.sh minimum` and
`bash scripts/test-ha-integration-matrix.sh current`.

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

Only one ZigbeeLens config entry/Core target is supported. The manifest declares
`single_config_entry: true`; config-flow concurrency checks and setup-time
singleton ownership remain as runtime defenses.

Monorepo staging for maintainers:

```bash
./scripts/package-hacs-repo.sh
```

Output: `dist/zigbeelens-hacs/`. It is a generated validation/install stage,
not a repository to push. Satellite synchronization requires its own separate
authorization; Phase 7D installation and final publication remain later,
separately authorized gates.

### Core URL and embedded view

The Core URL is the address Home Assistant uses to reach ZigbeeLens Core.

HTTP Core URLs are the normal Docker path and work for the native companion panel, entities, repairs, diagnostics, and **Open Full Dashboard**.

The optional embedded dashboard view usually requires an **HTTPS Core URL** when Home Assistant is served over HTTPS. Change the Core URL through **Reconfigure** — no need to delete and re-add the integration.

See [docs/hacs-embedded-view.md](../../docs/hacs-embedded-view.md) for HTTPS reverse proxy options (Traefik on Beast, Caddy example, etc.).

## Authorized pre-release validation from the synchronized satellite

This route is for maintainers performing Phase 7D release validation only. Use
it only after a separately authorized synchronization makes the exact generated
tree the reviewed `theaussiepom/zigbeelens-hacs` tree, `SOURCE_COMMIT` plus that
generated Git tree identify the exact candidate, both exact Home Assistant
lanes and generated official HACS/hassfest validation pass remotely on that
tree, the final artifact pairing is frozen, and separate explicit Phase 7D
installation authorization is recorded.

Then add `https://github.com/theaussiepom/zigbeelens-hacs` as a HACS Integration
custom repository and select the exact reviewed satellite commit. Use `main`
only if its explicitly reviewed tip is that exact commit and tree immediately
before installation. Never accept a floating or unreviewed branch, and do not
let HACS automatically select `v0.1.13` or another existing release.

This maintainer-only install is not a release or publication, does not provide
general installation support, and does not authorize the `v0.1.14` tag or
GitHub release. If the reviewed commit or tree changes, remove the pre-release
installation or replace it as one unit only after renewed exact-tree review,
remote checks, and separate Phase 7D authorization. General users must wait
for final release authorization.

## Conditional general-public HACS installation

Normal public custom-repository installation is a future route only. Phase 7D
must be complete, `SOURCE_COMMIT` plus the generated Git tree must identify the
exact reviewed satellite candidate, exact Home Assistant `2025.1.0` / Python
`3.12` and Home Assistant `2026.7.3` / Python `3.14` coverage must pass,
generated official HACS and hassfest validation must pass remotely on that
tree, and final release authorization must require the `v0.1.14` tag and GitHub
release to point to that tree. The maintainer-only route above does not satisfy
these general-public gates.

Only after those gates close may general users add the synchronized
`https://github.com/theaussiepom/zigbeelens-hacs` repository in HACS.

## Configure

During setup you will be asked for:

| Option | Default | Description |
|--------|---------|-------------|
| Core URL | `http://localhost:8377` | Address of your ZigbeeLens Core dashboard — replace the default unless Core truly shares Home Assistant's network namespace. It must be reachable **from Home Assistant**. HTTP is fine for the native panel and **Open Full Dashboard**. Use HTTPS for the optional embedded view when Home Assistant uses HTTPS. |
| Core API token | blank | Optional. Same value as Core `security.api_token` when Core protects its API. Stored in Home Assistant config-entry data; sent only as a server-side `Authorization: Bearer` header. |
| Verify SSL | `false` | Verify the Core TLS certificate when enabled. |
| Panel enabled | `true` | Show the ZigbeeLens companion panel in the Home Assistant sidebar. |

Polling defaults to 60 seconds. **Configure** persists any selected
15–900-second value and panel visibility as the authoritative options result;
Home Assistant then performs one effective reload and recreates the coordinator
with that interval.

Examples: `http://192.168.1.10:8377`, `https://zigbeelens.example.com`

Setup validates public `GET /api/version` (product proof, no Authorization), then protected `GET /api/health` with the bearer when configured.

The Core URL must be an exact HTTP(S) origin with no path, query, fragment, or
embedded credentials.

| Flow | Use for |
|------|---------|
| **Configure** (options) | Panel visibility and polling interval |
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

Do not use `http://localhost:8377` as an add-on backend URL. The add-on is
deferred; use standalone Core at an origin reachable from Home Assistant.

## Home Assistant enrichment

The coordinator reads Core health/diagnostic data, configuration status,
Decision Dashboard, and capabilities. The enrichment manager separately reads
bounded `/api/v1/devices` inventory and owns the integration's only write:
strict `POST /api/v1/enrichment/homeassistant`. Explicit config-entry removal
may call the exact DELETE for the same resource. There is no generic mutation
method.

The manager reads the official HA device, entity, and area registries. HA
user-facing names and resolved areas are additional metadata; Core preserves
its Zigbee2MQTT friendly name, and the user rename is never identity. Every
published row contains a final exact `(network_id, ieee_address)` identity.
Duplicate-IEEE candidates fail closed unless reviewed original registry-name
evidence selects exactly one Core row.

A complete accepted empty snapshot clears enrichment. Unavailable/partial HA
registry or Core inventory, unsupported capability, and transient HTTP failure
send no replacement, so Core retains the last accepted snapshot. The manager
owns initial sync, debounced registry events, bounded retry, and forced
15-minute reconciliation; unload cancels every listener/timer/task and reload
does not clear accepted data.

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

Missing or malformed Core versions fail closed as **Unknown**. Older, newer,
and malformed Decision contracts and missing/malformed exact-v2 Dashboard
Decision data have distinct states and repair guidance; a newer contract tells
the operator to update the integration, and payload-shape failure does not
prescribe a Core upgrade. Authentication alone owns reauthentication.

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
- During authorized maintainer-only pre-release validation, do not upgrade to a
  floating or automatically selected release. Remove or replace the exact
  reviewed installation if its commit or tree changes, then renew exact-tree
  review, remote checks, and Phase 7D authorization before reinstalling.
- Normal HACS-managed upgrades apply only after the final synchronized artifact
  is released and authorized for general users.

## Safety and security

This integration is read-only toward Zigbee control. It never publishes device-control MQTT commands (permit join, remove/reset, bind/unbind, OTA, channel changes, or device `/set`).

The HACS integration is **not** an authentication layer for ZigbeeLens Core. If your Core URL is reachable by users or networks you do not trust, consider firewall rules, network isolation, Home Assistant Ingress, or an authenticated reverse proxy. HTTPS Core URLs support optional embedded view in the browser; **HTTPS is not authentication**.

Some Core API routes modify ZigbeeLens local data only (reports, topology snapshots, HA enrichment). When topology capture is enabled in Core, Core itself may publish only the allowlisted Zigbee2MQTT network-map request used for observation — that is Core topology policy, not an HACS action. See [docs/security.md](../../docs/security.md).
