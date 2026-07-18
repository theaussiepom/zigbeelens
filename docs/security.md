# Security

Security model for ZigbeeLens Core configuration and runtime posture.

For vulnerability reporting see [SECURITY.md](../SECURITY.md).

## Current runtime posture

ZigbeeLens is read-only with respect to Zigbee control. It does not perform device-control actions such as permit join, remove, reset, bind/unbind, OTA, or channel changes.

Some API routes can modify ZigbeeLens’ own local data, such as creating/deleting reports, requesting a topology snapshot, or storing Home Assistant enrichment metadata.

When an API token is configured, Core requires authentication for protected
reads, mutations, SSE, and report downloads. Direct API clients use:

```http
Authorization: Bearer <token>
```

When both `security.api_token` and `security.session_secret` are configured,
same-origin browsers may exchange that bearer token for a short-lived HttpOnly
session cookie. Cookie-authenticated mutations also require:

```http
X-ZigbeeLens-CSRF-Token: <csrf-token>
```

CORS credential support, CSP/framing hardening, bundled UI login wiring, HACS
token support, and Home Assistant ingress identity validation are **not**
implemented yet. Browser sessions are same-origin only.

Bearer and session authentication authenticate the HTTP request. They do **not**
replace TLS on untrusted networks.

## Security modes

Configured under `security.mode` (or `ZIGBEELENS_SECURITY_MODE`):

| Mode | Meaning | What this build enforces |
|------|---------|--------------------------|
| `local` without `api_token` | Trusted-open compatibility | All API routes open. No session/CSRF. Strong warning when bound non-loopback. |
| `local` with `api_token` only | Bearer-only | Bearer required for protected routes |
| `local` with `api_token` + `session_secret` | Bearer + browser sessions | Bearer or HttpOnly session; CSRF on cookie mutations |
| `authenticated` | Credentials required in config | `api_token` mandatory; optional `session_secret` enables browser sessions |
| `home_assistant_ingress` | Intended HA ingress deploy | Temporary bearer/session fallback (`api_token` mandatory). Ingress identity headers are **not** trusted yet. |

Missing required credentials fail closed at config load. Core does **not** auto-generate secrets at startup and does not persist generated secrets into SQLite or YAML.

## Public HTTP surface

When authentication is active, only these endpoints are unauthenticated:

| Endpoint | Purpose |
|----------|---------|
| `GET /healthz` | Minimal readiness (`{"status":"ok"}` or degraded `503`) |
| `GET /api/version` | Product name/version |
| `GET /api/v1/version` | Same as `/api/version` |
| `GET /api/auth/session` | Minimal browser session status |
| `GET /api/v1/auth/session` | Same as `/api/auth/session` |
| Static UI shell / `/assets/*` | Bundled dashboard assets |
| CORS preflight | Handled by existing middleware |

Everything else under `/api` and `/api/v1` requires Bearer and/or a valid
browser session when a token is configured — including detailed `/api/health`,
`/api/config/status`, Dashboard, SSE, reports, and downloads.

## Bearer authentication

Accepted header:

```http
Authorization: Bearer <exact-token>
```

Rules:

- `Authorization: Bearer` is the only accepted bearer channel
- Scheme comparison is case-insensitive (`Bearer` / `bearer`)
- Token comparison is constant-time
- Query-string, cookie, and legacy-header credentials are rejected
- The former `X-ZigbeeLens-Api-Key` HTTP header is **not** accepted
- Missing and invalid credentials return the same `401` with `WWW-Authenticate: Bearer`

Core redacts recognised secret query parameter values from its own Uvicorn
access logs (for example `token`, `api_key`, `access_token`). That does **not**
sanitize reverse-proxy or load-balancer logs, which may record request URLs
before Core sees them. Credentials must never be placed in URLs.

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

## Browser sessions and CSRF

Browser sessions are enabled only when **both** `api_token` and `session_secret`
are configured. A session secret alone does nothing.

Optional settings:

| Setting | Default | Notes |
|---------|---------|-------|
| `security.session_ttl_seconds` | `43200` (12h) | Bounds: 300–604800; fixed non-sliding expiry |
| `security.session_cookie_secure` | `null` (automatic) | `null` → Secure false on loopback, true otherwise |

Cookie contract (`zigbeelens_session`):

- HttpOnly, SameSite=Strict, Path=/
- no Domain attribute
- never contains the API token or CSRF token
- signed with HMAC-SHA256 via `itsdangerous` (integrity, not confidentiality)

Session login (bearer bootstrap only):

```bash
curl -s -c cookies.txt -X POST http://127.0.0.1:8377/api/auth/session \
  -H "Authorization: Bearer $ZIGBEELENS_TEST_API_TOKEN" \
  | python3 -m json.tool
```

Authenticated read with the cookie jar (SSE/downloads work the same way):

```bash
curl -s -b cookies.txt http://127.0.0.1:8377/api/dashboard | python3 -m json.tool
```

Cookie-authenticated mutation (CSRF from login/status JSON):

```bash
CSRF=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["csrf_token"])' \
  < <(curl -s -b cookies.txt http://127.0.0.1:8377/api/auth/session))
curl -s -b cookies.txt -X POST http://127.0.0.1:8377/api/reports \
  -H "Content-Type: application/json" \
  -H "X-ZigbeeLens-CSRF-Token: $CSRF" \
  -d '{"scope":"full","format":"json","redaction":{"profile":"public_safe"}}' \
  | python3 -m json.tool
```

Logout clears the browser cookie. Stolen cookies remain usable until expiry
unless `api_token` or `session_secret` is rotated. Rotating either invalidates
all existing sessions. The bundled UI is not wired to login yet; HACS does not
use browser sessions.

## Canonical secret environment variables

Prefer environment or file injection over YAML:

| Variable | Purpose |
|----------|---------|
| `ZIGBEELENS_SECURITY_MODE` | Override `security.mode` |
| `ZIGBEELENS_SECURITY_API_TOKEN` | API token value |
| `ZIGBEELENS_SECURITY_API_TOKEN_FILE` | Path to API token file |
| `ZIGBEELENS_SECURITY_SESSION_SECRET` | Session signing secret |
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
