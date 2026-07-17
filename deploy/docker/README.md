# Standalone Docker deployment

Production container image for ZigbeeLens Core + bundled UI.

## Build

From repository root:

```bash
chmod +x scripts/build-docker.sh scripts/validate-compose.sh deploy/docker/entrypoint.sh
./scripts/build-docker.sh
```

Image tags:

- `ghcr.io/theaussiepom/zigbeelens:latest`
- `ghcr.io/theaussiepom/zigbeelens:0.1.0`

> **TODO:** Replace `zigbeelens` with your GHCR owner when the repository is published.

## Run

```bash
mkdir -p config data
cp deploy/docker/config.example.yaml config/config.yaml
# edit config/config.yaml

docker run --rm -p 8377:8377 \
  -v "$(pwd)/config:/config:ro" \
  -v "$(pwd)/data:/data" \
  ghcr.io/theaussiepom/zigbeelens:latest
```

## Compose

```bash
docker compose -f deploy/docker/docker-compose.example.yaml up -d
```

See also:

- `docker-compose.mosquitto.example.yaml` — optional local broker (most users already have one)
- `docker-compose.traefik.example.yaml` — subdomain reverse proxy
- `docker-compose.beast-traefik.example.yaml` — Beast Traefik HTTPS route (optional embedded view)
- `docker-compose.caddy.example.yaml` + `Caddyfile.example` — **optional** HTTPS reverse proxy for HACS **Try Embedded View** ([docs/hacs-embedded-view.md](../../docs/hacs-embedded-view.md))

## Container layout

| Path | Purpose |
|------|---------|
| `/config/config.yaml` | User configuration (mount read-only) |
| `/data/zigbeelens.sqlite` | SQLite database + stored reports |
| `/app/static` | Bundled UI (built at image build time) |
| `/entrypoint.sh` | Startup script |

## vs Home Assistant add-on

| | Standalone Docker | HAOS add-on |
|--|-------------------|-------------|
| Config | `/config/config.yaml` (you edit) | Generated from add-on options |
| Data | `/data` volume | `/data` (Supervisor managed) |
| UI access | Port **8377** or reverse proxy | Home Assistant **Ingress** |
| Image | `deploy/docker/Dockerfile` | `apps/addon/zigbeelens/Dockerfile` |

Both run the same ZigbeeLens product.

## Security

ZigbeeLens Core currently configures typed security settings and an optional mutation-route API-key guard; read routes, downloads, and SSE remain open. Publishing `8377:8377` exposes Core on the Docker host — convenient for local or trusted-network use. If Core is reachable beyond users or networks you trust, access-control decisions are your responsibility. HTTPS (optional, for embedded view) is not authentication. See [docs/security.md](../../docs/security.md).

## Validation

```bash
./scripts/validate-compose.sh
```

## Documentation

- [docs/docker.md](../../docs/docker.md) — install, security, troubleshooting
- [docs/hacs-embedded-view.md](../../docs/hacs-embedded-view.md) — optional HTTPS reverse proxy for HACS embedded view
- [docs/upgrades.md](../../docs/upgrades.md)
- [docs/backups.md](../../docs/backups.md)
