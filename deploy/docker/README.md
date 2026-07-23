# Standalone Docker deployment

Current portable deployment route for ZigbeeLens Core + bundled UI.

## Image channels

- `latest` — latest tagged release.
- `X.Y.Z` — the matching tagged release.
- `edge` / `main` — rolling current `main` for pre-release validation.
- `sha-*` — a traceable workflow-built commit.

An `edge` image is not a tagged release and does not prove that remote release
validation passed.

## Released/stable run

The default below is `latest`, the newest tagged release:

```bash
mkdir -p config data
cp deploy/docker/config.example.yaml config/config.yaml
# edit config/config.yaml

docker run --rm -p 8377:8377 \
  -v "$(pwd)/config:/config:ro" \
  -v "$(pwd)/data:/data" \
  ghcr.io/theaussiepom/zigbeelens:latest
```

Pin `:0.1.13` instead of `:latest` for a reproducible released install.

### Compose

```bash
mkdir -p zigbeelens/config zigbeelens/data
cp deploy/docker/docker-compose.example.yaml zigbeelens/docker-compose.yaml
cp deploy/docker/config.example.yaml zigbeelens/config/config.yaml
# Edit zigbeelens/config/config.yaml.
cd zigbeelens
docker compose up -d
```

Keep the copied Compose file beside `config/` and `data/`: relative bind mounts
are resolved from the Compose file's directory.

## Current-main/pre-release

The same maintained Compose file accepts an explicit image override:

```bash
cd zigbeelens
export ZIGBEELENS_IMAGE=ghcr.io/theaussiepom/zigbeelens:edge
docker compose pull
docker compose up -d
```

Use `main` as the equivalent rolling alias or `sha-*` when one exact workflow
artifact is required. Keep the selector set for future Compose operations.

## Build the current checkout locally

From the repository root:

```bash
chmod +x scripts/build-docker.sh scripts/validate-compose.sh deploy/docker/entrypoint.sh
ZIGBEELENS_IMAGE=zigbeelens:local ./scripts/build-docker.sh
```

Set `ZIGBEELENS_IMAGE=zigbeelens:local` when using the maintained Compose
example, or use that exact local tag with `docker run`.

Replace `theaussiepom` with your GHCR owner when using a fork.

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

| | Standalone Docker | Source-built HAOS add-on |
|--|-------------------|--------------------------|
| Config | `/config/config.yaml` (you edit) | Generated from add-on options |
| Data | `/data` volume | `/data` (Supervisor managed) |
| UI access | Port **8377** or reverse proxy | Home Assistant **Ingress** |
| Image source | `deploy/docker/Dockerfile` | `apps/addon/zigbeelens/Dockerfile` |

Both run the same ZigbeeLens product.

The current image-based add-on repository instead points at the standalone
GHCR image built from `deploy/docker/Dockerfile`. That publication path remains
blocked pending the startup-contract and HAOS smoke gates in the release
checklist.

## Security

ZigbeeLens Core supports bearer authentication and, when a session secret is
also configured, browser-session login. The example defaults to trusted-open
local/no-token mode. Publishing `8377:8377` exposes Core on all Docker-host
interfaces; use `127.0.0.1:8377:8377` for loopback-only access or configure
authentication and appropriate network controls. HTTPS (optional, for embedded
view) is not authentication. See [docs/security.md](../../docs/security.md).

## Validation

```bash
ZIGBEELENS_REQUIRE_DOCKER_COMPOSE=1 ./scripts/validate-compose.sh
```

## Documentation

- [docs/docker.md](../../docs/docker.md) — install, security, troubleshooting
- [docs/hacs-embedded-view.md](../../docs/hacs-embedded-view.md) — optional HTTPS reverse proxy for HACS embedded view
- [docs/upgrades.md](../../docs/upgrades.md)
- [docs/backups.md](../../docs/backups.md)
