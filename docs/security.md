# Security

Security model for ZigbeeLens v0.1.0.

For vulnerability reporting see [SECURITY.md](../SECURITY.md).

## v0.1.0 posture

ZigbeeLens Core does **not** include built-in authentication in v0.1.0.

ZigbeeLens is read-only with respect to Zigbee control. It does not perform device-control actions such as permit join, remove, reset, bind/unbind, OTA, or channel changes.

Some API routes can modify ZigbeeLens’ own local data, such as creating/deleting reports, requesting a topology snapshot, or storing Home Assistant enrichment metadata. If you expose Core beyond users or networks you trust, access-control decisions are your responsibility.

For broader access, consider firewall rules, Home Assistant Ingress, network isolation, or an authenticated reverse proxy such as Authentik, Cloudflare Access, Authelia, or basic auth. HTTPS may help with the optional embedded dashboard view in Home Assistant, but **HTTPS is not authentication**.

## Local-first design

- No cloud sync or external telemetry
- All history in local SQLite on your host
- MQTT collector is subscribe-only
- Optional publishers are restricted to allowlisted topics

## Network exposure

| Install | Exposure |
|---------|----------|
| HAOS add-on | Via Home Assistant Ingress — inherits HA access controls |
| Docker standalone | Port 8377 when published — convenient for local/trusted-network use; access control is the operator’s responsibility if exposure is broader |
| Dev | Localhost by default |

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

If your Core URL is reachable by users or networks you do not trust, consider firewall rules, network isolation, Home Assistant Ingress, or an authenticated reverse proxy.

## Reverse proxy notes

When proxying ZigbeeLens:

- Preserve SSE (`/api/events/stream`) or rely on UI polling fallback
- Terminate TLS at the proxy — TLS is not authentication
- Add authentication at the proxy if Core is reachable beyond users or networks you trust

## Related

- [docker.md](docker.md)
- [hacs.md](hacs.md)
- [hacs-embedded-view.md](hacs-embedded-view.md)
- [addon-dev.md](addon-dev.md)
- [redaction.md](redaction.md)
