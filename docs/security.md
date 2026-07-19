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
Origin: <Core or allowed browser origin>
X-ZigbeeLens-CSRF-Token: <csrf-token>
```

Direct bearer clients do **not** need `Origin` or CSRF.

### Browser origins, CORS, and framing

Core accepts only canonical HTTP/HTTPS origins (`scheme://host[:port]`). No
wildcards, regexes, userinfo, paths, query strings, or fragments.

| Setting | Purpose |
|---------|---------|
| `security.cors_allowed_origins` | Exact browser-visible origins allowed for credentialed CORS and session-mutation `Origin` checks |
| `security.frame_ancestor_origins` | Exact external origins (for example Home Assistant) allowed to embed Core HTML |

These lists are independent. Configuring one never copies entries into the other.

Framing defaults to same-origin only (`frame-ancestors 'self'`). A Home
Assistant origin needed only for iframe embedding belongs in
`frame_ancestor_origins`; it does **not** automatically grant CORS or API
access. CORS is not authentication.

### TLS-terminating reverse proxies

The canonical first-party Core launcher runs Uvicorn with forwarding-header
trust disabled (`proxy_headers=False`). `X-Forwarded-Proto`,
`X-Forwarded-For`, and `Forwarded` do **not** rewrite the ASGI request scheme,
client, or Host used for Origin validation. External ASGI runners must likewise
disable forwarding-header rewriting unless they intentionally own a reviewed
proxy-trust policy. Trusted reverse-proxy networks and Home Assistant ingress
identity remain deferred.

Behind a TLS-terminating proxy, Core commonly sees:

```text
scheme=http
Host=zigbeelens.example
```

while the browser-visible `Origin` is:

```text
https://zigbeelens.example
```

For browser sessions, operators must explicitly allow that browser-visible
origin (this does **not** trust the proxy and does **not** grant framing):

```yaml
security:
  cors_allowed_origins:
    - https://zigbeelens.example
```

A common reverse-proxy plus HACS iframe deployment uses both lists for different
jobs:

```yaml
security:
  cors_allowed_origins:
    - https://zigbeelens.example   # browser Origin for session/CORS
  frame_ancestor_origins:
    - https://homeassistant.example  # HA page allowed to frame Core HTML
```

Core sends Content-Security-Policy on HTML documents, plus `nosniff`,
`Referrer-Policy: no-referrer`, and a restrictive `Permissions-Policy`. Core
does **not** set HSTS (TLS proxies own that). Reverse proxies must not broaden
Core’s CORS or frame policy with wildcards.

The bundled standalone UI checks public browser-session status before loading
protected data. When browser sessions are enabled, the UI exchanges an API token
once for an HttpOnly session cookie and does not persist the token. The HACS
integration may store the same Core API token and send it only from Home
Assistant’s server-side HTTP client (never in panel/iframe URLs). Home
Assistant ingress identity validation is **not** implemented yet.

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
access logs (for example `token`, `api_key`, `access_token`, and the fixed
`zigbeelens_session` cookie name if it appears as a query key). That does
**not** sanitize reverse-proxy or load-balancer logs, which may record request
URLs before Core sees them. Credentials must never be placed in URLs.

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

Cookie-authenticated mutation (exact Origin + CSRF from login/status JSON):

```bash
CSRF=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["csrf_token"])' \
  < <(curl -s -b cookies.txt http://127.0.0.1:8377/api/auth/session))
curl -s -b cookies.txt -X POST http://127.0.0.1:8377/api/reports \
  -H "Origin: http://127.0.0.1:8377" \
  -H "Content-Type: application/json" \
  -H "X-ZigbeeLens-CSRF-Token: $CSRF" \
  -d '{"scope":"full","format":"json","redaction":{"profile":"public_safe"}}' \
  | python3 -m json.tool
```

Logout clears the browser cookie. Stolen cookies remain usable until expiry
unless `api_token` or `session_secret` is rotated. Rotating either invalidates
all existing sessions. The standalone UI verifies the cookie round-trip after
login, keeps CSRF only in memory for mutations, uses credentialed SSE and
report downloads, and never places credentials in URLs. HACS uses bearer
authentication for its server-side Core client; browser Open Full Dashboard /
embedded view still use standalone session login.

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
| Bundled UI | Trusted-open enters directly | Token login when `session_secret` is set; bearer-only Core shows setup-required |
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

- Home Assistant ingress identity validation
- Trusted reverse-proxy / forwarded-header identity
