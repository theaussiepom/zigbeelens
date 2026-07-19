# Docker install

Run ZigbeeLens as a standalone container with Docker or Compose — no Home Assistant required.

ZigbeeLens serves the **same diagnostic console** as the HAOS add-on: Core API + bundled UI on port **8377**, SQLite persistence under `/data`, read-only MQTT collection, and redacted reports.

## Quick start

```bash
mkdir -p zigbeelens/config zigbeelens/data
cp deploy/docker/config.example.yaml zigbeelens/config/config.yaml
# Edit zigbeelens/config/config.yaml — set mqtt.server and networks[].base_topic

cd zigbeelens
docker compose -f ../deploy/docker/docker-compose.example.yaml up -d
```

Open **http://localhost:8377**

Or build locally:

```bash
./scripts/build-docker.sh
docker run --rm -p 8377:8377 \
  -v "$(pwd)/config:/config:ro" \
  -v "$(pwd)/data:/data" \
  ghcr.io/theaussiepom/zigbeelens:latest
```

## Configuration

Copy `deploy/docker/config.example.yaml` to `config/config.yaml`.

| Setting | Description |
|---------|-------------|
| `mqtt.server` | Broker URI, e.g. `mqtt://192.168.1.10:1883` or `mqtt://mosquitto:1883` in Compose |
| `mqtt.username` / `mqtt.password` | Optional broker credentials |
| `networks[].id` | Stable identifier — **do not change casually** (stored in history) |
| `networks[].name` | Display label only |
| `networks[].base_topic` | Zigbee2MQTT base topic (must match exactly) |
| `storage.path` | Use `/data/zigbeelens.sqlite` in containers |
| `storage.retention_days` | Keep collected telemetry for this many days (default **7**; purged on startup) |

### Multiple Zigbee2MQTT networks

Add one `networks[]` entry per Zigbee2MQTT instance. See `deploy/docker/config.multi-network.example.yaml`.

- Each `base_topic` becomes a monitored network
- `id` must be stable — device identity is `network_id + ieee_address`
- `name` is cosmetic; friendly names may collide across networks

## Volumes

| Mount | Purpose |
|-------|---------|
| `/config` (read-only) | `config.yaml` |
| `/data` (read-write) | SQLite database, stored reports, runtime state |

**Run one Core instance per SQLite database.** Do not mount the same `/data` volume into multiple containers — migrations and writes are not safe across concurrent processes.

Ensure `/data` is writable by container UID **1000** (`zigbeelens` user):

```bash
sudo chown -R 1000:1000 data
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ZIGBEELENS_CONFIG` | `/config/config.yaml` | Config file path |
| `ZIGBEELENS_STATIC_DIR` | `/app/static` | Bundled UI assets |
| `ZIGBEELENS_LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` |
| `ZIGBEELENS_PORT` | — | Optional compatibility override for `server.port` (resolved into typed AppConfig before bind) |
| `ZIGBEELENS_OPENAPI_ENABLED` | `false` | Set `true` to expose `/docs` and `/openapi.json` (dev/debug only) |
| `ZIGBEELENS_SECURITY_MODE` | — | Override `security.mode` (`local`, `authenticated`, `home_assistant_ingress`) |
| `ZIGBEELENS_SECURITY_API_TOKEN` / `_FILE` | — | API bearer token (prefer over YAML) |
| `ZIGBEELENS_SECURITY_SESSION_SECRET` / `_FILE` | — | Browser-session signing secret (with API token) |
| `ZIGBEELENS_SECURITY_SESSION_SECRET` / `_FILE` | — | Session secret (configured only; unused by HTTP layer yet) |
| `ZIGBEELENS_MQTT_USERNAME` | — | MQTT username override |
| `ZIGBEELENS_MQTT_PASSWORD` / `_FILE` | — | MQTT password override |
| `ZIGBEELENS_API_KEY` | — | Temporary alias for the API token (conflicts with canonical token vars) |
| `TZ` | — | Timezone for logs/display |

Secrets may come from environment or `*_FILE` paths. They are **never logged**. See [security.md](security.md).

Core’s process default bind is loopback (`127.0.0.1`). The `zigbeelens` launcher binds exactly `AppConfig.server.host` / `server.port` (including `ZIGBEELENS_PORT` when set). Docker example configs explicitly set `server.host: 0.0.0.0` inside the container. Publishing `8377` on the host is **not** fully authenticated yet — prefer `127.0.0.1:8377:8377` or a trusted authenticated reverse proxy. See [security.md](security.md).

## Health check

The image defines a built-in `HEALTHCHECK` (`deploy/docker/Dockerfile`) that calls public `GET /healthz` on loopback. Compose files do not repeat it — Docker inherits the check from the image.

The probe uses `ZIGBEELENS_PORT` when set, otherwise **8377**. It does **not** load AppConfig or secret files and does **not** send a bearer token. The Docker image default remains 8377; example Compose files continue to publish `8377:8377`. Detailed `GET /api/health` remains available for diagnostics and is bearer-protected when an API token is configured.

If you override the internal listening port with `ZIGBEELENS_PORT` (merged into typed AppConfig before Uvicorn binds), you must also align:

- container-side Compose port mappings / published ports;
- any reverse-proxy upstream target;
- the healthcheck environment (inherited automatically when `ZIGBEELENS_PORT` is set on the service).

Server status and Uvicorn always share one effective AppConfig bind.

Healthy means:
- App is running
- Database is reachable
- Migrations applied

**MQTT collector disconnected does not fail the healthcheck.** Temporary broker outages should not restart the container; the UI explains collector status.

## Compose examples

| File | Use case |
|------|----------|
| `docker-compose.example.yaml` | Standalone ZigbeeLens (most users) |
| `docker-compose.mosquitto.example.yaml` | Local broker for testing — **most HA users already have Mosquitto** |
| `docker-compose.traefik.example.yaml` | Subdomain reverse proxy |
| `docker-compose.beast-traefik.example.yaml` | Beast Traefik HTTPS route for optional embedded view |
| `docker-compose.caddy.example.yaml` | **Optional:** HTTPS reverse proxy for HACS embedded view (see [hacs-embedded-view.md](../hacs-embedded-view.md)) |
| `Caddyfile.example` | Caddy config for the example above (SSE-friendly) |

Validate examples:

```bash
./scripts/validate-compose.sh
```

## Reverse proxy / Traefik

**Recommended:** subdomain (`zigbeelens.example.com` → container `:8377`).

ZigbeeLens Core supports typed security configuration, bearer authentication, optional browser sessions, exact CORS/frame-ancestor allowlists, and HTML Content-Security-Policy. First-party Core ignores `X-Forwarded-*` / `Forwarded` headers: behind a TLS-terminating proxy the browser-visible Origin is typically `https://…` while Core sees `http` + `Host`. Put that browser-visible origin in `security.cors_allowed_origins` for session/CORS (this does not trust the proxy). Configure framing for a Home Assistant iframe separately with `security.frame_ancestor_origins` (canonical `https://homeassistant.example` style origins only). Proxies should not broaden Core CORS/CSP with wildcards; TLS/HSTS remain proxy responsibilities. The bundled UI uses browser-session login when both API token and session secret are configured. HACS token support and ingress identity enforcement have not landed. If Core is reachable beyond users or networks you trust, access-control decisions are your responsibility — for example firewall rules, network isolation, Home Assistant Ingress, or an authenticated reverse proxy / VPN.

### Beast / Authentik split routing

If the UI is behind Authentik, **do not** protect `/api` with the same middleware chain — Home Assistant config flow and the coordinator call `/api/health` and other read-only endpoints without a browser session. Use a higher-priority Traefik router for `PathPrefix(/api)` with `local@file` only (see `deploy/traefik/zigbeelens-router.yaml.example`, mirroring ThreadLens).

### Correct Core URLs (Beast example)

| Use | URL |
|-----|-----|
| Default HACS / LAN | `http://192.168.100.5:8377` |
| Optional HTTPS / iframe | `https://zigbeelens.theaussiepom.me` |
| **Wrong** | `https://zigbeelens.theaussiepom.me:8377` |

Traefik HTTPS is on port **443**. The `:8377` suffix on an HTTPS hostname bypasses Traefik and will not work as intended.

For Traefik + live updates (SSE):
- Prefer subdomain routing over path prefixes
- Disable response buffering for the ZigbeeLens service if updates stall
- Report downloads use relative URLs; copy Markdown from the UI if downloads fail through a proxy

### Optional: HTTPS for HACS embedded view

If Home Assistant uses **HTTPS** and Core uses plain **HTTP** (`http://host:8377`), browsers block **Try Embedded View** in the HACS companion panel (mixed content). That is expected — **Open Full Dashboard** still works in a new tab.

To enable embedded view, put Core behind HTTPS and point the integration **Core URL** at that HTTPS URL. The repo includes a self-contained Caddy stack:

- `deploy/docker/docker-compose.caddy.example.yaml`
- `deploy/docker/Caddyfile.example` (includes `flush_interval -1` for SSE)

Full setup, certificate trust, and security notes: **[HACS embedded view — optional HTTPS reverse proxy](hacs-embedded-view.md)**.

## Security

ZigbeeLens Core may require `Authorization: Bearer` for protected API routes when an API token is configured. See [security.md](security.md).

- ZigbeeLens is **read-only** toward Zigbee2MQTT — no device commands, permit join, remove, reset, bind/unbind, or OTA
- Some API routes modify **ZigbeeLens local data only** (reports, topology snapshots, HA enrichment metadata)
- Reports are redacted before storage/download
- Publishing `8377:8377` exposes Core on the Docker host — convenient for local or trusted-network use
- If Core is reachable by users or networks you do not trust, access-control decisions are your responsibility (firewall rules, network isolation, Home Assistant Ingress, or an authenticated reverse proxy)
- HTTPS helps with optional HACS embedded view browser requirements; **HTTPS is not authentication**
- No Docker socket, privileged mode, or host networking in default examples

## Image tags

Published images (when available):

```
ghcr.io/theaussiepom/zigbeelens:latest
ghcr.io/theaussiepom/zigbeelens:0.1.0
ghcr.io/theaussiepom/zigbeelens:<git-sha>
```

Replace `zigbeelens` with your GHCR owner when using a fork.

## Troubleshooting

### UI loads but no devices

- Confirm Zigbee2MQTT is running and publishing to the configured `base_topic`
- Check Settings → collector status in the UI
- Verify MQTT host/port from inside the container network

### Wrong base topic

`networks[].base_topic` must match Zigbee2MQTT exactly (no trailing slash).

### MQTT connection failed

- Test broker reachability from the container network
- Check username/password in config
- For TLS, set `mqtt.tls.enabled: true` and use `mqtts://` in `mqtt.server`

### Availability missing

Enable availability in Zigbee2MQTT if you rely on online/offline detection.

### Duplicate friendly names

Expected — friendly names are not globally unique. Identity is `network_id + ieee_address`.

### Collector disconnected

Broker may be down or credentials wrong. Container stays healthy; fix MQTT and watch the UI reconnect.

### Database permission errors

Ensure `/data` is writable by UID 1000.

### Reports not downloading

Try **Copy Markdown** in the Reports page. Check reverse proxy buffering settings.

### Live updates stale behind proxy

SSE may be blocked — the UI falls back to 30s polling. Configure proxy for SSE or use subdomain routing.

## Related docs

- [Upgrades](upgrades.md)
- [Backups](backups.md)
- [HACS embedded view (optional HTTPS reverse proxy)](hacs-embedded-view.md)
- [Add-on dev (HAOS)](../docs/addon-dev.md)
- [MQTT dev](mqtt-dev.md)
