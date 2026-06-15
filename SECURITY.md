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

## v0.1.0 security posture

ZigbeeLens Core does **not** include built-in authentication in v0.1.0.

ZigbeeLens is read-only with respect to Zigbee control. It does not perform device-control actions such as permit join, remove, reset, bind/unbind, OTA, or channel changes.

Some API routes can modify ZigbeeLens’ own local data, such as creating/deleting reports, requesting a topology snapshot, or storing Home Assistant enrichment metadata. If you expose Core beyond users or networks you trust, access-control decisions are your responsibility.

For broader access, consider firewall rules, Home Assistant Ingress, network isolation, or an authenticated reverse proxy such as Authentik, Cloudflare Access, Authelia, or basic auth. HTTPS may help with the optional embedded dashboard view in Home Assistant, but **HTTPS is not authentication**.

## Design principles

ZigbeeLens is **local-first**:

- No cloud sync or telemetry backhaul
- Data stored in local SQLite on your host
- MQTT collector is subscribe-only by default
- Optional publishers (MQTT Discovery, topology) are restricted to allowlisted topic prefixes

## Secrets and redaction

- MQTT passwords, tokens, and network keys must not appear in logs or stored reports
- Reports are redacted **before** storage and download
- Use the `public_safe` redaction profile when sharing reports on GitHub or forums
- Never paste raw `config.yaml` or full MQTT payloads into public issues

See [docs/redaction.md](docs/redaction.md) and [docs/security.md](docs/security.md).

## Deployment guidance

| Install | Notes |
|---------|-------|
| HAOS add-on | Full dashboard via Home Assistant Ingress — inherits your HA access controls |
| Docker standalone | Publishing port 8377 exposes Core on the Docker host; convenient for local or trusted-network use |
| HACS integration | Not an authentication layer for Core; HTTPS Core URLs are for embedded-view browser compatibility, not auth |

If Core is reachable by users or networks you do not trust, consider firewall rules, network isolation, Home Assistant Ingress, or an authenticated reverse proxy.

## Out of scope for v0.1.0

Built-in login, API tokens, and session authentication are intentionally **not** included in v0.1.0. Operators choose how to expose Core and whether to add access control around it.
