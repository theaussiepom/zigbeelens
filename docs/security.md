# Security

Security model for ZigbeeLens Core configuration and runtime posture.

For vulnerability reporting see [SECURITY.md](../SECURITY.md).

## Current runtime posture

ZigbeeLens is read-only with respect to Zigbee control. It does not perform device-control actions such as permit join, remove, reset, bind/unbind, OTA, or channel changes.

Some API routes can modify ZigbeeLens’ own local data, such as creating/deleting reports, requesting a topology snapshot, or storing Home Assistant enrichment metadata.

When an API token is configured, Core requires:

```http
Authorization: Bearer <token>
```

for protected reads, mutations, SSE, and report downloads. Browser sessions/CSRF, CORS/CSP hardening, bundled UI login, HACS token support, and Home Assistant ingress identity validation are **not** implemented yet.

Bearer authentication authenticates the HTTP request. It does **not** replace TLS on untrusted networks.

## Security modes

Configured under `security.mode` (or `ZIGBEELENS_SECURITY_MODE`):

| Mode | Meaning | What this build enforces |
|------|---------|--------------------------|
| `local` without `api_token` | Trusted-open compatibility | All API routes open (public + protected). Strong warning when bound non-loopback. |
| `local` with `api_token` | Local deploy with a shared secret | Bearer required for all protected API routes |
| `authenticated` | Credentials required in config | Bearer required for all protected API routes (`api_token` mandatory) |
| `home_assistant_ingress` | Intended HA ingress deploy | Temporary bearer fallback (`api_token` mandatory). Ingress identity headers are **not** trusted yet. |

Missing required credentials fail closed at config load. Core does **not** auto-generate secrets at startup and does not persist generated secrets into SQLite or YAML.

## Public HTTP surface

When bearer authentication is active, only these endpoints are unauthenticated:

| Endpoint | Purpose |
|----------|---------|
| `GET /healthz` | Minimal readiness (`{"status":"ok"}` or degraded `503`) |
| `GET /api/version` | Product name/version |
| `GET /api/v1/version` | Same as `/api/version` |
| Static UI shell / `/assets/*` | Bundled dashboard assets |
| CORS preflight | Handled by existing middleware |

Everything else under `/api` and `/api/v1` requires Bearer when a token is configured — including detailed `/api/health`, `/api/config/status`, Dashboard, SSE, reports, and downloads.

## Bearer authentication

Accepted header:

```http
Authorization: Bearer <exact-token>
```

Rules:

- Scheme comparison is case-insensitive (`Bearer` / `bearer`)
- Token comparison is constant-time
- Tokens are not accepted from query strings, cookies, URL fragments, or form bodies
- The former `X-ZigbeeLens-Api-Key` HTTP header is **not** accepted
- Missing and invalid credentials return the same `401` with `WWW-Authenticate: Bearer`

Generate a token safely:

```bash
openssl rand -base64 48
```

API tokens must be ASCII bearer-compatible (`token68`: letters, digits, and
`-._~+/`, with optional `=` padding only at the end), 32–4096 characters, with
no spaces, commas, or control characters. Prefer `openssl rand -base64 48` or a
URL-safe random string.

Example:

```bash
curl -s http://127.0.0.1:8377/api/dashboard \
  -H "Authorization: Bearer $ZIGBEELENS_TEST_API_TOKEN"
```

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

`ZIGBEELENS_API_KEY` remains a temporary **configuration-source** alias for `security.api_token`.

It does **not** restore the removed `X-ZigbeeLens-Api-Key` HTTP header. Clients must send `Authorization: Bearer`.

It **must not** be combined with `ZIGBEELENS_SECURITY_API_TOKEN` or `ZIGBEELENS_SECURITY_API_TOKEN_FILE`.

### `*_FILE` rules

- Paths expand `~`
- Must be a regular readable file
- Decoded as UTF-8
- Only trailing CR/LF characters are stripped
- Empty content, missing files, unreadable paths, invalid UTF-8, and control characters fail closed
- Error messages may mention the path, never the secret contents

## Token validation

`api_token` and `session_secret` (when set):

- reject empty strings
- reject leading/trailing whitespace
- reject NUL/control characters
- require at least 32 characters
- never echo rejected values in validation errors or logs

## Bind address defaults

- Process default `server.host` is `127.0.0.1`
- Explicit `0.0.0.0` / `::` remains valid for containers and add-ons
- Docker/add-on example configs keep an explicit container bind

`/api/config/status` exposes secret-free posture metadata (`mode`, loopback bind, bearer flags, trusted-local-open). It never returns token values, lengths, fingerprints, or secret file paths.

## Client compatibility notes

| Client | `local` without token | Token configured / `authenticated` |
|--------|------------------------|------------------------------------|
| Direct API (`curl`, scripts) | Open | Use `Authorization: Bearer` |
| Bundled UI | Works | Login/token attachment not implemented yet |
| HACS integration | Works | Token configuration not implemented yet |

Do not weaken bearer protection to preserve unauthenticated clients in authenticated mode.

## Health probes

| Endpoint | Auth | Contents |
|----------|------|----------|
| `GET /healthz` | Always public | Minimal `status` only — used by Docker HEALTHCHECK |
| `GET /api/health` | Protected when bearer required | Detailed collector/topology/enrichment status |

## Network exposure

| Install | Exposure |
|---------|----------|
| HAOS add-on | Via Home Assistant Ingress — inherits HA access controls; Core ingress-identity enforcement is not active yet |
| Docker standalone | Port 8377 when published — prefer loopback publish or a trusted authenticated reverse proxy |
| Dev | Loopback by default |

For broader access today, consider firewall rules, Home Assistant Ingress, network isolation, or an authenticated reverse proxy. HTTPS may help with embedding, but **HTTPS is not authentication**.

## Not yet implemented

- Browser sessions and CSRF
- Bundled UI authentication
- HACS token configuration
- Home Assistant ingress identity validation
- CORS/CSP/origin hardening beyond the current embed CSP note
