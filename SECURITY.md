# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

Security fixes are released for the latest 0.1.x patch when applicable.

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities, credential leaks, or unredacted secrets.**

Instead:

1. Open a **private** security advisory on GitHub (preferred), or
2. Contact the maintainers through your usual secure channel if you already have one.

Include:

- Affected version
- Install path (HAOS add-on, Docker, local dev)
- Steps to reproduce
- Impact assessment
- Any sample data — use `public_safe` redaction only

We aim to acknowledge reports within a reasonable timeframe and will coordinate disclosure.

## Current security posture

ZigbeeLens Core includes typed security configuration (`security.mode`, API token, session secret) with environment and `*_FILE` secret loading for API, session, and MQTT credentials.

When `security.api_token` is configured, Core requires authentication for
protected reads, mutations, SSE event streams, and report downloads. Direct
clients use `Authorization: Bearer`. When `security.session_secret` is also
configured, same-origin browsers may create an HttpOnly session cookie; cookie
mutations require an exact browser `Origin` and `X-ZigbeeLens-CSRF-Token`. The
former `X-ZigbeeLens-Api-Key` HTTP header is not accepted.

`security.mode=local` without a token is a deliberate trusted-open compatibility
mode (all API routes open). `authenticated` requires an API token.
`home_assistant_ingress` authenticates the add-on UI from the exact Supervisor
ingress peer (`X-Remote-User-Id`); an API token is optional bearer fallback for
HACS/direct clients only.

Public without a token:

- `GET /healthz`
- `GET /api/version` and `GET /api/v1/version`
- `GET /api/auth/session` and `GET /api/v1/auth/session`
- Static UI assets

ZigbeeLens is read-only with respect to Zigbee control. It does not perform device-control actions such as permit join, remove, reset, bind/unbind, OTA, or channel changes.

Some API routes can modify ZigbeeLens’ own local data. If you expose Core beyond users or networks you trust, access-control decisions are your responsibility.

Exact CORS and frame-ancestor allowlists, Content-Security-Policy on HTML, and
canonical HACS Core URL validation are implemented. The bundled standalone UI
uses browser-session login (HttpOnly cookie + in-memory CSRF) when both
`api_token` and `session_secret` are configured. The Home Assistant add-on UI
uses Supervisor ingress identity (no browser token). The HACS integration can
store the same optional Core API token for server-side bearer reads. HTTPS may
help with the optional embedded dashboard view, but **HTTPS is not
authentication**.

The source add-on implements that Ingress contract. Its current image-based
release package is not publication-ready: optional token-file propagation is
missing and the packaged HAOS artifact still needs `/data` writability and
Ingress smoke validation.

See [docs/security.md](docs/security.md).

## Design principles

ZigbeeLens is **local-first**:

- No cloud sync or telemetry backhaul
- Data stored in local SQLite on your host
- MQTT collector is subscribe-only by default
- Topology is restricted to the exact allowlisted network-map request; MQTT
  Discovery normal publishes are topic-validated, but its broker last-will
  registration ordering remains an open release blocker

## Secrets and redaction

- MQTT passwords, tokens, and network keys must not appear in logs or stored reports
- Prefer environment or `*_FILE` injection over YAML for secrets
- Reports are redacted **before** storage and download
- Use the `public_safe` redaction profile when sharing reports on GitHub or forums
- Never paste raw `config.yaml` or full MQTT payloads into public issues

See [docs/redaction.md](docs/redaction.md) and [docs/security.md](docs/security.md).

## Deployment guidance

| Install | Notes |
|---------|-------|
| HAOS add-on | Full dashboard via Home Assistant Ingress; Core accepts the injected identity only from the exact Supervisor peer and uses proxy-only ingress mode |
| Docker standalone | Publishing port 8377 exposes Core on the Docker host; convenient for local or trusted-network use |
| HACS integration | Not an authentication layer for Core; HTTPS Core URLs are for embedded-view browser compatibility, not auth |

If Core is reachable by users or networks you do not trust, consider firewall rules, network isolation, Home Assistant Ingress, or an authenticated reverse proxy.
