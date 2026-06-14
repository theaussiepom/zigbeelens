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

- Standalone Docker exposes the dashboard on port 8377 — use a trusted LAN or reverse proxy with authentication
- Home Assistant Ingress inherits your HA access controls
- Do not expose ZigbeeLens directly to the public internet without appropriate access controls

## Out of scope

ZigbeeLens intentionally does **not** implement authentication in v0.1.0. Treat network placement and reverse-proxy auth as part of your security model for standalone installs.
