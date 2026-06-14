# Security

Security model for ZigbeeLens v0.1.0.

For vulnerability reporting see [SECURITY.md](../SECURITY.md).

## Local-first design

- No cloud sync or external telemetry
- All history in local SQLite on your host
- MQTT collector is subscribe-only
- Optional publishers are restricted to allowlisted topics

## Network exposure

| Install | Exposure |
|---------|----------|
| HAOS add-on | Via Home Assistant Ingress — inherits HA auth |
| Docker standalone | Port 8377 — **use trusted LAN or reverse proxy** |
| Dev | Localhost only by default |

ZigbeeLens v0.1.0 does **not** include built-in authentication for standalone Docker. Treat network placement and reverse-proxy authentication as part of your security model.

## Secrets handling

- MQTT credentials live in config YAML only
- Secrets are not written to application logs
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

## Data at rest

- SQLite database at `storage.path` (default `/data/zigbeelens.sqlite` in containers)
- Stored reports are already redacted
- Back up `/data` and `/config` — see [backups.md](backups.md)

Ensure `/data` permissions are correct (UID 1000 in Docker).

## Home Assistant integration

- Read-only HTTP to Core
- Diagnostics platform returns redacted data
- Does not mutate Zigbee or Zigbee2MQTT

## Reverse proxy notes

When proxying ZigbeeLens:

- Preserve SSE (`/api/events/stream`) or rely on UI polling fallback
- Terminate TLS at the proxy
- Add authentication if exposed beyond trusted LAN

## Related

- [docker.md](docker.md)
- [addon-dev.md](addon-dev.md)
- [redaction.md](redaction.md)
