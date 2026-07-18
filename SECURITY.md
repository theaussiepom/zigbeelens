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
mutations require `X-ZigbeeLens-CSRF-Token`. The former `X-ZigbeeLens-Api-Key`
HTTP header is not accepted.

`security.mode=local` without a token is a deliberate trusted-open compatibility
mode (all API routes open). `authenticated` and `home_assistant_ingress` require
an API token; ingress identity headers are not trusted yet.

Public without a token:

- `GET /healthz`
- `GET /api/version` and `GET /api/v1/version`
- `GET /api/auth/session` and `GET /api/v1/auth/session`
- Static UI assets

ZigbeeLens is read-only with respect to Zigbee control. It does not perform device-control actions such as permit join, remove, reset, bind/unbind, OTA, or channel changes.

Some API routes can modify ZigbeeLens’ own local data. If you expose Core beyond users or networks you trust, access-control decisions are your responsibility.

Bundled UI login wiring, credentialed CORS, HACS token configuration, and Home
Assistant ingress identity enforcement are not implemented yet. HTTPS may help
with the optional embedded dashboard view, but **HTTPS is not authentication**.

See [docs/security.md](docs/security.md).

## Design principles

ZigbeeLens is **local-first**:

- No cloud sync or telemetry backhaul
- Data stored in local SQLite on your host
- MQTT collector is subscribe-only by default
- Optional publishers (MQTT Discovery, topology) are restricted to allowlisted topic prefixes

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
| HAOS add-on | Full dashboard via Home Assistant Ingress — inherits your HA access controls; Core ingress-identity enforcement is not active yet |
| Docker standalone | Publishing port 8377 exposes Core on the Docker host; convenient for local or trusted-network use |
| HACS integration | Not an authentication layer for Core; HTTPS Core URLs are for embedded-view browser compatibility, not auth |

If Core is reachable by users or networks you do not trust, consider firewall rules, network isolation, Home Assistant Ingress, or an authenticated reverse proxy.
