# ZigbeeLens

**Read-only diagnostics for Zigbee2MQTT networks.**

Understand your Zigbee mesh before you change it.

ZigbeeLens is a read-only observability and diagnostic console for Zigbee2MQTT
networks. It watches Zigbee2MQTT over MQTT, keeps local history, evaluates
stored evidence into a shared **decision** vocabulary, and generates redacted
reports for troubleshooting. Its job is to show what is worth reviewing, why,
which evidence supports that judgement, and what the available data cannot
prove.

ZigbeeLens is part of the **Lens family** of read-only home-network observability tools, alongside [ThreadLens](https://github.com/theaussiepom/threadlens). The active public diagnostic contract is **decision contract v2** (not retired Lens-bucket fields); see [docs/api.md](docs/api.md) and [docs/lens-family.md](docs/lens-family.md).

ZigbeeLens does **not** repair, reset, remove, re-pair, or mutate Zigbee devices.

## What it is

- Read-only observability for Zigbee2MQTT
- Decision-led Overview with priorities, recent changes, and coverage limits
- Mesh / Investigate workspace for evidence-led network investigation
- Device Story and snapshot history on Device Detail
- Multi-network support (`network_id` + `ieee_address` identity)
- Local SQLite history and stored reports
- Redacted JSON, YAML, and Markdown exports
- Docker/Compose as the current portable deployment route; HACS integration
  and Home Assistant OS add-on source are present for pre-release testing, but
  their publication gates remain open
- Optional MQTT Discovery decision summary entities
- Optional topology snapshots and Home Assistant enrichment

## What it is not

- Not a Zigbee controller
- Not a Zigbee2MQTT replacement
- Not a repair tool
- Not a root-cause oracle
- Not a Lovelace dashboard recipe

## Key safety promises

- Does not remove devices
- Does not reset devices
- Does not permit join
- Does not change channels
- Does not configure, bind, or unbind devices
- Does not run OTA
- Does not publish Zigbee2MQTT `set` or device-control requests; the only
  allowlisted Zigbee2MQTT request is `bridge/request/networkmap`
- Topology is enabled by default for one startup scan after collector/bridge
  readiness; periodic capture stays off unless configured, and manual capture
  requires confirmation
- Reports are redacted before storage and download

See [docs/safety-audit.md](docs/safety-audit.md) for the full safety audit.

## Install

| Path | Current status | Artifact |
|------|----------------|----------|
| [Docker / Compose](docs/docker.md) | **Current portable deployment route**; choose released `latest`/`X.Y.Z` or explicit pre-release `edge`/`sha-*` | `ghcr.io/theaussiepom/zigbeelens` |
| [Home Assistant integration](docs/hacs.md) | **Local/staged source testing only — public HACS satellite unsynchronized and publication blocked** | Generated `dist/zigbeelens-hacs/custom_components/zigbeelens` package |
| [Home Assistant OS add-on](apps/addon/zigbeelens/README.md) | **Pre-release source — generated repository publication blocked** | Source-built runner and generated image-based package have different open gates |
| [MQTT Discovery](docs/mqtt-discovery.md) | Optional summary HA entities without HACS | Core configuration |
| [Topology](docs/topology.md) | Optional mesh enrichment — enabled by default with one startup scan | Core configuration |

## Using the UI

The primary navigation follows the normal investigation journey:

1. **Overview** — start with what needs review first, what changed, and where
   evidence coverage is limited.
2. **Mesh / Investigate** — explore one network around the evidence ZigbeeLens
   identified.
3. **Devices** — find a device and open its Device Story and snapshot history.
4. **Incidents** — review correlated issue records without treating them as
   root-cause proof.
5. **Reports** — manage saved reports and create a full-estate report.
6. **Settings** — inspect Core, collector, storage, and feature status.

**Advanced & support** contains **Networks**, **Timeline**, **Topology
snapshots**, and **How it works**. Those surfaces retain useful raw or
operational detail without competing with the primary investigation flow.

## Quick start

### Home Assistant OS

The source add-on and Ingress runner exist, but the current image-based package
does not propagate its optional API-token option and has additional
configuration/reachability blockers. Do not publish or present that package as
a supported install until the gates in
[the release checklist](RELEASE_CHECKLIST.md) pass against HAOS. Use the Docker
path below for current deployment testing.

Details: [add-on user guide](apps/addon/zigbeelens/README.md) ·
[add-on development](docs/addon-dev.md)

### Docker

```bash
ZIGBEELENS_IMAGE=zigbeelens:local ./scripts/build-docker.sh
mkdir -p zigbeelens/config zigbeelens/data
cp deploy/docker/docker-compose.example.yaml zigbeelens/docker-compose.yaml
cp deploy/docker/config.example.yaml zigbeelens/config/config.yaml
# Edit zigbeelens/config/config.yaml — set mqtt.server and networks[].base_topic
cd zigbeelens
ZIGBEELENS_IMAGE=zigbeelens:local docker compose up -d
```

Open **http://localhost:8377**

This quick start builds the current checkout locally. For released or
workflow-built images, choose the channel explicitly in
[docs/docker.md](docs/docker.md).

### Home Assistant integration

**Local/staged source testing only.** The public HACS satellite is not
synchronized with the reviewed package and must not be used to validate this
branch. Generate and manually install the integration from this checkout as
described in [docs/hacs.md](docs/hacs.md). Synchronizing or publishing the
satellite requires a separate explicitly authorized task after its runtime,
version-identity, compatibility, and official-validation gates close.

The optional integration gives Home Assistant:

- a native ZigbeeLens companion panel
- summary sensors and binary sensors
- diagnostics and repairs
- a button to open the full ZigbeeLens dashboard

The full ZigbeeLens dashboard is served by ZigbeeLens Core.

For Docker users, an HTTP Core URL such as `http://192.168.1.10:8377` is fine. The native Home Assistant panel works, and the **Open Full Dashboard** button opens the full dashboard in a new tab.

The optional **Try Embedded View** button can show the full dashboard inside Home Assistant only when browser security allows it. In practice, if Home Assistant is served over HTTPS, the ZigbeeLens Core URL also needs to be HTTPS for embedded view to work.

You do not need HTTPS or a reverse proxy for the native, non-embedded companion
path. Change the Core URL under **Settings → Devices & services → ZigbeeLens →
Reconfigure**.

Details: [docs/hacs.md](docs/hacs.md) · [docs/hacs-embedded-view.md](docs/hacs-embedded-view.md)

## Configuration

Use the canonical [configuration reference](docs/configuration.md) for exact
option names, types, defaults, secret handling, and deployment-specific
availability. Installation examples link back to that reference instead of
maintaining separate option tables.

## Reports

Generate scoped diagnostic reports from the Reports page or `POST /api/reports`.

- **JSON** — structured data for tools
- **YAML** — human-readable structured export
- **Markdown** — forum and GitHub friendly

Redaction profiles: `standard`, `public_safe`, `strict`. Reports are redacted **before** storage and download.

Details: [docs/reports.md](docs/reports.md) · [docs/redaction.md](docs/redaction.md)

## Known limitations

- ZigbeeLens observes MQTT and Zigbee2MQTT data — it cannot prove RF interference.
- It cannot prove the current physical route. A topology snapshot is
  capture-time neighbour-table and route-hint evidence, not a live route map.
- Topology is point-in-time and may be slow or unavailable on large networks.
- Battery and LQI reporting vary by device firmware and configuration.
- Availability depends on Zigbee2MQTT `availability` feature being enabled.
- Some sleepy end devices report infrequently by design.
- Diagnostics use correlation language — not definitive root-cause claims.

## Security model

ZigbeeLens Core includes typed security configuration and secret loading
(environment / `*_FILE`). When an API token is configured, protected API
routes (reads, mutations, SSE, downloads) require `Authorization: Bearer
<token>` and/or a valid browser session. With `session_secret` also configured,
browsers can create an HttpOnly session cookie (exact `Origin` + CSRF required
for cookie mutations). The image-based add-on package generates Supervisor
Ingress configuration, but its current entrypoint omits optional token-file
installation; token-enabled behavior is therefore not a packaged-release
claim. The HACS integration may store a Core token for server-side bearer reads
(never in panel/iframe URLs). Exact `cors_allowed_origins` /
`frame_ancestor_origins` allowlists and HTML Content-Security-Policy are
supported. `local` mode without a token remains deliberately trusted-open.
Generic `X-Forwarded-*` trust remains disabled.

ZigbeeLens is read-only with respect to Zigbee control. It does not perform device-control actions such as permit join, remove, reset, bind/unbind, OTA, or channel changes.

Some API routes can modify ZigbeeLens’ own local data, such as creating/deleting reports, requesting a topology snapshot, or storing Home Assistant enrichment metadata. If you expose Core beyond users or networks you trust, access-control decisions are your responsibility.

For broader access, consider firewall rules, Home Assistant Ingress, network isolation, or an authenticated reverse proxy such as Authentik, Cloudflare Access, Authelia, or basic auth. HTTPS may be useful for the optional embedded dashboard view, but **HTTPS is not authentication**.

Details: [docs/security.md](docs/security.md) · [SECURITY.md](SECURITY.md)

## Documentation

| Topic | Doc |
|-------|-----|
| Architecture | [docs/architecture.md](docs/architecture.md) |
| Configuration | [docs/configuration.md](docs/configuration.md) |
| Development | [docs/development.md](docs/development.md) |
| HAOS add-on | [docs/addon-dev.md](docs/addon-dev.md) |
| Docker | [docs/docker.md](docs/docker.md) |
| HACS | [docs/hacs.md](docs/hacs.md) |
| HACS embedded view (optional HTTPS) | [docs/hacs-embedded-view.md](docs/hacs-embedded-view.md) |
| MQTT Discovery | [docs/mqtt-discovery.md](docs/mqtt-discovery.md) |
| Topology | [docs/topology.md](docs/topology.md) |
| Reports | [docs/reports.md](docs/reports.md) |
| Redaction | [docs/redaction.md](docs/redaction.md) |
| Troubleshooting | [docs/troubleshooting.md](docs/troubleshooting.md) |
| Backups | [docs/backups.md](docs/backups.md) |
| Upgrades | [docs/upgrades.md](docs/upgrades.md) |
| Release | [docs/release.md](docs/release.md) |
| Pre-release smoke test | [docs/release-test.md](docs/release-test.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |

## API overview

**`/api/v1` is the preferred prefix for new integrations.** Legacy `/api/*` routes remain available. Details: [docs/api.md](docs/api.md).

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/health` | Core, collector, discovery, topology status |
| `GET /api/v1/capabilities` | Stable feature flags (no secrets) |
| `GET /api/v1/status` | Collector and storage summary |
| `GET /api/v1/dashboard` | Overview payload |
| `GET /api/v1/networks`, `/api/v1/devices`, `/api/v1/routers` | Inventory |
| `GET /api/v1/incidents`, `/api/v1/timeline` | Diagnostics |
| `GET/POST/DELETE /api/v1/reports*` | Redacted reports |
| `GET/POST /api/v1/topology*` | Optional topology (capture requires confirmation) |
| `GET/POST/DELETE /api/v1/enrichment/*` | Optional HA enrichment |
| `GET /api/v1/events/stream` | SSE live updates |

Interactive docs (when enabled): `http://localhost:8377/docs` — set `ZIGBEELENS_OPENAPI_ENABLED=true`.

## License

MIT — see [LICENSE](LICENSE)

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

Report security issues privately — see [SECURITY.md](SECURITY.md).
