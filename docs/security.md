# Security

Security model for ZigbeeLens Core configuration and runtime posture.

For vulnerability reporting see [SECURITY.md](../SECURITY.md).

## Current runtime posture

ZigbeeLens is read-only with respect to Zigbee control. It does not perform device-control actions such as permit join, remove, reset, bind/unbind, OTA, or channel changes.

Some API routes can modify ZigbeeLens’ own local data, such as creating/deleting reports, requesting a topology snapshot, or storing Home Assistant enrichment metadata.

**Important limitation in this release:** Core configuration now includes typed security settings and secret loading, but the only built-in HTTP protection that is active is the **legacy mutation-route API-key guard**. Read-only GET routes, report downloads, and SSE event streams remain open. Bearer authentication, browser sessions/CSRF, CORS/CSP hardening, and Home Assistant ingress identity validation are **not** enforced yet.

Do not treat `security.mode: authenticated` or `home_assistant_ingress` as fully enforced access control in this build.

## Security modes

Configured under `security.mode` (or `ZIGBEELENS_SECURITY_MODE`):

| Mode | Meaning in configuration | What this build enforces |
|------|--------------------------|--------------------------|
| `local` | Default local/trusted operation | Optional mutation-route API-key guard when an API token is configured |
| `authenticated` | Credentials are required in config (`api_token`) | Same mutation-route guard only; read routes/SSE remain open |
| `home_assistant_ingress` | Declares intended HA ingress deployment | Ingress identity validation is **not** active yet |

Missing required credentials fail closed at config load. Core does **not** auto-generate secrets at startup and does not persist generated secrets into SQLite or YAML.

## Optional mutation-route API key

When `security.api_token` is configured, mutating routes require header `X-ZigbeeLens-Api-Key`:

- `POST` / `DELETE` `/api/reports*`
- `POST` `/api/topology/{network_id}/capture`
- `POST` / `DELETE` `/api/enrichment/homeassistant`

(` /api/v1/...` aliases share the same policy.)

GET/HEAD/OPTIONS, SSE (`/api/events/stream`), and report downloads remain open.

## Canonical secret environment variables

Prefer environment or file injection over YAML:

| Variable | Purpose |
|----------|---------|
| `ZIGBEELENS_SECURITY_MODE` | Override `security.mode` |
| `ZIGBEELENS_SECURITY_API_TOKEN` | API token value |
| `ZIGBEELENS_SECURITY_API_TOKEN_FILE` | Path to API token file |
| `ZIGBEELENS_SECURITY_SESSION_SECRET` | Session secret value (reserved; unused by this build’s HTTP layer) |
| `ZIGBEELENS_SECURITY_SESSION_SECRET_FILE` | Path to session secret file |
| `ZIGBEELENS_MQTT_USERNAME` | MQTT username override |
| `ZIGBEELENS_MQTT_PASSWORD` | MQTT password override |
| `ZIGBEELENS_MQTT_PASSWORD_FILE` | Path to MQTT password file |

### Temporary compatibility alias

`ZIGBEELENS_API_KEY` remains a temporary alias for `security.api_token`.

It **must not** be combined with `ZIGBEELENS_SECURITY_API_TOKEN` or `ZIGBEELENS_SECURITY_API_TOKEN_FILE`. Conflicting sources raise a configuration error instead of guessing precedence.

### `*_FILE` rules

- Paths expand `~`
- Must be a regular readable file
- Decoded as UTF-8
- Only trailing CR/LF characters are stripped
- Empty content, missing files, unreadable paths, invalid UTF-8, and control characters fail closed
- Error messages may mention the path, never the secret contents

A direct environment value and its matching `*_FILE` variable must not both be set.

Environment/file values override YAML. YAML may still contain `security.api_token` / `security.session_secret`, but that is discouraged.

## Token validation

`api_token` and `session_secret` (when set):

- reject empty strings
- reject leading/trailing whitespace
- reject NUL/control characters
- require at least 32 characters
- never echo rejected values in validation errors or logs

### Generating a secret safely

Example:

```bash
openssl rand -base64 48
```

Store the result in an environment variable or a root-restricted file referenced by `*_FILE`. Do not commit tokens to git.

## Bind address defaults

- Process default `server.host` is `127.0.0.1`
- Explicit `0.0.0.0` / `::` remains valid for containers and add-ons
- Add-on generated config continues to bind `0.0.0.0`
- Docker example configs keep an explicit container bind and document host exposure separately

`/api/config/status` exposes secret-free posture metadata (`security.mode`, loopback bind, whether tokens are configured, whether the mutation guard is enabled). It never returns token values, secret lengths, fingerprints, or secret file paths.

## Network exposure

| Install | Exposure |
|---------|----------|
| HAOS add-on | Via Home Assistant Ingress — inherits HA access controls; Core ingress-identity enforcement is not active yet in this build |
| Docker standalone | Port 8377 when published — bind to loopback or place a trusted authenticated reverse proxy in front until broader Core auth lands |
| Dev | Loopback by default |

For broader access today, consider firewall rules, Home Assistant Ingress, network isolation, or an authenticated reverse proxy such as Authentik, Cloudflare Access, Authelia, or basic auth. HTTPS may help with embedding, but **HTTPS is not authentication**.

## Secrets handling

- Prefer env / `*_FILE` injection for MQTT and security secrets
- Secrets are not written to application logs
- Config validation errors omit rejected input values
- Reports are redacted before storage and download
- Use `public_safe` redaction when sharing reports publicly

See [redaction.md](redaction.md).

## MQTT safety

| Component | Publish behaviour |
|-----------|-------------------|
| Collector | **None** — subscribe only |
| MQTT Discovery | `homeassistant/` and `zigbeelens/` only |
| Topology | Single allowlisted `{base_topic}/bridge/request/networkmap` when explicitly enabled and confirmed |

ZigbeeLens does not publish device commands, permit join, remove, reset, bind, unbind, or OTA topics.

Audit: [safety-audit.md](safety-audit.md)

## Core API — local data only

These routes change ZigbeeLens’ own stored data, not Zigbee devices:

- `POST` / `DELETE` `/api/reports*`
- `POST` `/api/topology/{network_id}/capture` (allowlisted network-map request only, confirmation-gated)
- `POST` / `DELETE` `/api/enrichment/homeassistant`

Read-only observability endpoints (`/api/dashboard`, `/api/devices`, etc.) do not mutate Zigbee2MQTT or devices.

## Data at rest

- SQLite database at `storage.path` (default `/data/zigbeelens.sqlite` in containers)
- Stored reports are already redacted
- Back up `/data` and `/config` — see [backups.md](backups.md)

Ensure `/data` permissions are correct (UID 1000 in Docker).

## Home Assistant integration

- Read-only HTTP to Core for polling health and dashboard data
- The HACS integration is **not** an authentication layer for Core
- Diagnostics platform returns redacted data
- Does not mutate Zigbee or Zigbee2MQTT

HACS token configuration and add-on ingress trust options are separate follow-up work and are not configured here.

## Reverse proxy notes

When proxying ZigbeeLens:

- Preserve SSE (`/api/events/stream`) or rely on UI polling fallback
- Terminate TLS at the proxy — TLS is not authentication
- Add authentication at the proxy if Core is reachable beyond users or networks you trust

## Related

- [docker.md](docker.md)
- [troubleshooting.md](troubleshooting.md)
- [hacs.md](hacs.md)
- [hacs-embedded-view.md](hacs-embedded-view.md)
- [addon-dev.md](addon-dev.md)
- [redaction.md](redaction.md)
