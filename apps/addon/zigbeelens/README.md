# ZigbeeLens Home Assistant add-on

ZigbeeLens is a **read-only observability console** for Zigbee2MQTT.

It watches Zigbee2MQTT over MQTT, keeps local history in SQLite, classifies device and network health, correlates incidents, and generates **redacted diagnostic reports** you can share safely.

Open it from the Home Assistant sidebar after install — no extra ports, no Docker knowledge required.

## What it does

- Multi-network Zigbee2MQTT monitoring
- Live diagnostic dashboard (Overview, Incidents, Networks, Devices, Routers, Timeline)
- Evidence-backed incident correlation
- Redacted JSON / YAML / Markdown reports
- Persistent history under `/data`

## What it does **not** do

ZigbeeLens is **read-only**. It will never:

- Repair or reset devices
- Remove or re-pair devices
- Permit join
- Change Zigbee channels
- Publish Zigbee2MQTT commands or request topics
- Mutate Zigbee state

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

## Reports

Open **Reports** in the ZigbeeLens UI to generate snapshots:

- **JSON / YAML** — full structured diagnostic data
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

- `zigbeelens.sqlite` — telemetry, incidents, reports
- `config.yaml` — generated from your add-on options

Include the add-on in your **Home Assistant backup** so history and stored reports are preserved.

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
- Read-only MQTT subscriber — no publish, no request topics
- Same codebase as the Docker Compose / dev path

## Support

- Issues: https://github.com/theaussiepom/zigbeelens/issues
- Docs: [docs/addon-dev.md](../../../docs/addon-dev.md) (developers)
