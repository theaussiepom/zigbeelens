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
| `ZIGBEELENS_PORT` | `8377` | Listen port (usually leave default) |
| `TZ` | — | Timezone for logs/display |

Secrets are read from config YAML only — they are **never logged**.

## Health check

The image defines a built-in `HEALTHCHECK` (`deploy/docker/Dockerfile`) that calls `GET /api/health`. Compose files do not repeat it — Docker inherits the check from the image.

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

ZigbeeLens has **no built-in authentication**. Keep it on a trusted LAN or behind an authenticated reverse proxy / VPN.

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

- ZigbeeLens is **read-only** toward Zigbee2MQTT — no publish, no request topics, no device commands
- Reports are redacted before storage/download
- Do **not** expose port 8377 to the public internet without authentication
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
