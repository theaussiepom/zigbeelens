# ZigbeeLens Home Assistant add-on

ZigbeeLens is a **read-only observability console** for Zigbee2MQTT.

It watches Zigbee2MQTT over MQTT, keeps local history in SQLite, runs the shared Decision Engine, and generates **redacted evidence reports** you can share safely.

Open it from the Home Assistant sidebar after install — no extra ports, no Docker knowledge required.

The add-on **runs ZigbeeLens Core itself**. Home Assistant Ingress shows the full canonical Core UI (Overview, Mesh investigations, Devices, Incidents, Reports). There is no separate add-on decision layer. The optional HACS integration can sit alongside the add-on for entities, repairs, and the companion panel; its decision contract talks to Core over HTTP and is not an internal add-on presentation path.

## What it does

- Multi-network Zigbee2MQTT monitoring
- Live Core dashboard via Ingress (Overview, Mesh, Devices, Incidents, Reports)
- Shared Decision Engine: investigation priorities, Device Stories, data coverage warnings
- Evidence-backed incident correlation
- Redacted JSON / YAML / Markdown evidence reports
- Persistent history under `/data`

## What it does **not** do

ZigbeeLens is **read-only for Zigbee control**. It never publishes device-control commands:

- Permit join
- Remove / reset / re-pair devices
- Bind / unbind
- OTA firmware updates
- Channel changes
- Device `/set` commands

When topology policy allows it, Core may publish **only** the allowlisted Zigbee2MQTT network-map request used for topology observation. Default add-on policy keeps topology observational:

- topology enabled
- startup scan enabled
- periodic refresh disabled
- manual / automatic / incident-driven capture disabled unless you change options

MQTT Discovery remains optional and **disabled by default**.

## Install

1. **Settings → Add-ons → Add-on store → ⋮ → Repositories**
2. Add this repository URL (when published):
   ```
   https://github.com/theaussiepom/zigbeelens-addons
   ```
   For local development, see [docs/addon-dev.md](../../../docs/addon-dev.md).
3. Install **ZigbeeLens**.
4. Configure MQTT and your Zigbee2MQTT network(s) (see below).
5. **Start** the add-on.
6. Open **ZigbeeLens** from the sidebar (Home Assistant Ingress).

## Configuration

### MQTT

| Option | Description |
|--------|-------------|
| `mqtt.host` | MQTT broker hostname. Use `core-mosquitto` for the official Mosquitto add-on. |
| `mqtt.port` | Broker port (usually `1883`). |
| `mqtt.username` | Optional username. |
| `mqtt.password` | Optional password (stored in add-on config, never logged). |
| `mqtt.tls.enabled` | Use `mqtts://` when `true`. |
| `mqtt.tls.reject_unauthorized` | Reject invalid TLS certificates when `true`. |

### Networks

Each Zigbee2MQTT instance needs one network entry:

| Option | Description |
|--------|-------------|
| `networks[].id` | Stable identifier (e.g. `home`, `shed`). |
| `networks[].name` | Friendly label shown in the UI. |
| `networks[].base_topic` | Zigbee2MQTT base topic (e.g. `zigbee2mqtt`). |

**One network:**

```yaml
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt
```

**Two networks:**

```yaml
networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt

  - id: shed
    name: Shed
    base_topic: zigbee2mqtt-shed
```

### Advanced options

Diagnostics thresholds, report limits, and feature flags are available under **Diagnostics**, **Reporting**, and **Features** in the add-on configuration UI. Defaults are sensible for most homes.

- `features.mqtt_discovery` — leave **off** unless you want optional Home Assistant MQTT Discovery entities (see [docs/mqtt-discovery.md](../../../docs/mqtt-discovery.md)). The HACS integration is recommended for native HA entities.
- `features.manual_network_map` — leave **off** unless you use manual topology snapshots.
- `features.automatic_network_map` — leave **off** (not supported).

### Storage retention

| Option | Default | Meaning |
|--------|---------|---------|
| `storage.retention_days` | `7` | Telemetry history only (metrics, availability, snapshots, events, unresolved messages, terminal topology). Does **not** govern reports or incidents. |
| `storage.resolved_incident_retention_days` | `90` | Resolved incidents. Use `0` in add-on options for Core `null` (kept indefinitely). Open/watching incidents are never age-purged. |
| `storage.report_retention_days` | `0` | Reports. Add-on `0` → Core `null` (kept until manually deleted). Set a positive day count only if you want opt-in auto-retention. |
| `storage.maintenance_interval_hours` | `24` | Periodic maintenance interval after the startup cycle. |

Maintenance runs at Core startup (after migrations + integrity gates) and on the interval above. There is **no Purge / Vacuum / Backup button** in the UI — Settings shows policy and last-maintenance facts only. See [docs/backups.md](../../../docs/backups.md).

Local Core CLI (outside the add-on container, against a copied DB or stopped instance):

- `zigbeelens storage check` / `storage maintenance --dry-run` — truly non-mutating (read-only open; dry-run does not update status)
- `zigbeelens storage maintenance --apply` — runs retention; does **not** run migrations (Core startup owns migrations)

## Reports

Open **Reports** in the ZigbeeLens UI to generate snapshots:

- **JSON / YAML** — full structured evidence and decision data
- **Markdown** — GitHub / forum friendly summary

Redaction profiles:

| Profile | Use when |
|---------|----------|
| **Standard** | Default; secrets redacted, names mostly preserved |
| **Public safe** | Sharing on GitHub or community forums |
| **Strict** | Maximum privacy |

Secrets (MQTT passwords, tokens, network keys) are **always** redacted before storage or download.

## Data & backups

All persistent data lives under `/data/zigbeelens/` inside the add-on:

- `zigbeelens.sqlite` — telemetry, incidents, reports (reports stay until you delete them unless you set finite `report_retention_days`)
- `config.yaml` — generated from your add-on options

Include the add-on in your **Home Assistant backup** so history and stored reports are preserved. For online SQLite snapshots from a running Core process, use `zigbeelens storage backup` (symlink-safe atomic publish); see [docs/backups.md](../../../docs/backups.md).

## Troubleshooting

### MQTT collector disconnected

- Confirm Mosquitto (or your broker) is running.
- Check `mqtt.host` — use `core-mosquitto` for the official add-on.
- Verify username/password if the broker requires auth.
- Check add-on logs: **Settings → Add-ons → ZigbeeLens → Log**.

### No devices appearing

- Confirm Zigbee2MQTT is running and publishing to the configured `base_topic`.
- Wait for the bridge `devices` list message after Zigbee2MQTT starts.
- Ensure `features.mqtt_collector` is enabled.

### Wrong base topic

Each network's `base_topic` must match Zigbee2MQTT's `base_topic` setting exactly (no trailing slash).

### Availability missing

Zigbee2MQTT must publish `availability` topics if you rely on online/offline detection. Check Zigbee2MQTT `availability` settings.

### Ingress UI not loading

- Confirm the add-on is **started** and healthy.
- Hard-refresh the browser (Ingress caches aggressively).
- Check logs for startup errors.

### Live updates feel stale

ZigbeeLens uses Server-Sent Events for live refresh. Some proxies block SSE; the UI falls back to polling every 30 seconds and shows a disconnected indicator.

### Reports look empty

If Zigbee2MQTT has just started, wait for telemetry to arrive. An empty network still produces a valid report explaining that no data has been collected yet.

## Architecture notes

- Single container: Core API + bundled UI on port **8377**
- Home Assistant **Ingress** proxies the UI into the sidebar
- Read-only MQTT subscriber by default — the collector does not publish to Zigbee2MQTT topics. Optional MQTT Discovery and topology capture can publish when explicitly enabled in options.
- Same codebase as the Docker Compose / dev path

## Security

The add-on dashboard is served through Home Assistant **Ingress** (admin-only panel). Supervisor injects a validated user identity; ZigbeeLens Core trusts it only from the exact Supervisor ingress peer. No API token is required to open the ingress UI. An optional add-on `security.api_token` enables HACS/direct bearer API access and is stored in a secret file (never in generated `config.yaml`). Direct browser access outside ingress is denied. See [docs/security.md](../../../docs/security.md).

## Support

- Issues: https://github.com/theaussiepom/zigbeelens/issues
- Docs: [docs/addon-dev.md](../../../docs/addon-dev.md) (developers)
