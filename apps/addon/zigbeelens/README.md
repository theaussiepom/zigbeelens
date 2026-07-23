# ZigbeeLens Home Assistant add-on

ZigbeeLens is a **read-only observability console** for Zigbee2MQTT.

It watches Zigbee2MQTT over MQTT, keeps local history in SQLite, runs the shared
Decision Engine, and generates **redacted evidence reports** designed for
sharing after you review the export.

## Release status — generated repository publication blocked

This repository contains two different add-on paths:

- the **source-built add-on runner**, available for local/source development;
- the **generated image-based repository**, which selects the standalone GHCR
  image and is not publication-ready.

Do not present the generated repository as a supported release install. Its
open gates include the complete runner/option contract, optional API-token
propagation, HAOS UID-1000 `/data` writability, Supervisor Ingress and spoof
rejection, reporting schema/default/unused-control alignment, and a portable
HACS-to-Core origin. Structural package validation does not close those live
HAOS and runtime gates.

The source-built runner is intended to run ZigbeeLens Core and show the
canonical UI through Home Assistant Ingress. There is no separate add-on
decision layer. HACS is not required for that UI. The optional HACS integration
can add entities, repairs, and a companion panel only when Home Assistant can
reach a separate Core HTTP origin; Ingress itself is not that origin.

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

## Conditional public-repository install

Use these steps only after the generated repository is published and every
publication gate above is closed. For current source development, use
[docs/addon-dev.md](../../../docs/addon-dev.md) instead.

1. **Settings → Add-ons → Add-on store → ⋮ → Repositories**
2. Add this repository URL:
   ```
   https://github.com/theaussiepom/zigbeelens-addons
   ```
3. Install **ZigbeeLens**.
4. Configure MQTT and your Zigbee2MQTT network(s) (see below).
5. **Start** the add-on.
6. Open **ZigbeeLens** from the sidebar (Home Assistant Ingress).

## Configuration

### MQTT

| Option | Default | Description |
|--------|---------|-------------|
| `mqtt.host` | `core-mosquitto` | MQTT broker hostname. Use `core-mosquitto` for the official Mosquitto add-on. |
| `mqtt.port` | `1883` | Broker port. |
| `mqtt.username` | blank | Optional username. |
| `mqtt.password` | blank | Optional password (stored in add-on config, never logged). |
| `mqtt.tls.enabled` | `false` | Generates an `mqtts://` broker URI when `true`. |
| `mqtt.tls.reject_unauthorized` | `true` | Reject invalid TLS certificates when `true`. |

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

### Diagnostics and reporting defaults

| Option | Default |
|--------|---------|
| `diagnostics.incident_window_seconds` | `180` |
| `diagnostics.stale_after_hours` | `24` |
| `diagnostics.low_battery_percent` | `20` |
| `diagnostics.weak_link_threshold` | `40` |
| `diagnostics.flapping_threshold` | `3` |
| `diagnostics.recently_unstable_window_hours` | `24` |
| `diagnostics.bridge_stale_after_minutes` | `10` |
| `diagnostics.mains_stale_after_hours` | `12` |
| `diagnostics.battery_stale_after_hours` | `48` |
| `diagnostics.incident_watch_window_minutes` | `30` |
| `diagnostics.incident_resolution_grace_minutes` | `5` |
| `diagnostics.network_wide_device_percent` | `25` |
| `diagnostics.network_wide_min_devices` | `5` |
| `diagnostics.correlated_min_devices` | `2` |
| `diagnostics.stale_cluster_min_devices` | `3` |
| `diagnostics.low_battery_cluster_min_devices` | `3` |
| `diagnostics.interview_failure_min_devices` | `2` |
| `reporting.default_profile` | `standard` |
| `reporting.max_recent_events` | `100` |
| `reporting.max_metric_samples_per_device` | `50` |
| `reporting.max_availability_changes_per_device` | `50` |
| `reporting.include_raw_payloads` | `false` |

Use values of at least `1` for all three `reporting.max_*` limits. The current
Supervisor schema incorrectly accepts `0`, but Core rejects it at startup.
`reporting.default_profile` is accepted by the schema, but the current report
request path defaults to `standard` independently; select a non-standard
redaction profile explicitly when generating a report.
`reporting.max_metric_samples_per_device`,
`reporting.max_availability_changes_per_device`, and
`reporting.include_raw_payloads` are also accepted but have no current
exact-v3 composition effect.

### Feature, discovery, and topology defaults

| Option | Default | Notes |
|--------|---------|-------|
| `features.mqtt_collector` | `true` | Collect Zigbee2MQTT telemetry. |
| `features.mqtt_discovery` | `false` | First of two required discovery switches. |
| `features.bridge_logs` | `true` | Observe bridge log messages. |
| `features.device_payload_history` | `true` | Retain device payload history. |
| `features.manual_network_map` | `false` | Also required for manual topology capture. |
| `features.automatic_network_map` | `false` | Legacy automatic-map gate; keep off unless deliberately enabling periodic capture. |
| `mqtt_discovery.enabled` | `false` | Second required discovery switch. |
| `mqtt_discovery.topic_prefix` | `homeassistant` | Discovery topic prefix. |
| `mqtt_discovery.state_topic_prefix` | `zigbeelens` | Entity state topic prefix. |
| `mqtt_discovery.retain` | `true` | Retain discovery messages. |
| `mqtt_discovery.device_name` | `ZigbeeLens` | Home Assistant device label. |
| `mqtt_discovery.object_id_prefix` | `zigbeelens` | Compatibility option; the current summary publisher ignores custom values and uses fixed `zigbeelens_<entity-key>` object IDs. |
| `topology.enabled` | `true` | Enables topology policy. |
| `topology.startup_scan` | `true` | Requests one allowlisted network map after startup delay. |
| `topology.startup_stable_delay_seconds` | `60` | Delay before startup scan. |
| `topology.refresh_interval_seconds` | `0` | Periodic refresh disabled. |
| `topology.manual_capture_enabled` | `false` | Also requires `features.manual_network_map`. |
| `topology.automatic_capture_enabled` | `false` | Periodic automatic capture disabled. |
| `topology.automatic_capture_interval_hours` | `24` | Legacy periodic interval when both automatic gates are enabled and `refresh_interval_seconds` is `0`. |
| `topology.capture_on_incident` | `false` | Reserved in the current runtime; leave disabled. |
| `topology.max_snapshots_per_network` | `30` | Per-network snapshot cap. |
| `topology.warn_before_capture` | `true` | Compatibility setting; the manual confirmation flow remains enforced. |

MQTT Discovery publishes only when both discovery switches are true. Periodic
topology capture requires the corresponding feature and topology gates; the
default startup scan is independent and may publish the allowlisted
Zigbee2MQTT network-map request.

Keep the Discovery state prefix at its default: the broker last will is
currently registered before normal topic validation. Also keep the topology
refresh interval at `0` if topology is disabled; a positive interval can make
scheduler status appear active while the capture service rejects requests.

Add-on option changes are read at process startup. Restart the add-on after
changing configuration.

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

### Upgrade or remove

- Before an upgrade, create a Home Assistant backup that includes ZigbeeLens.
  Update from the add-on store, restart, and check the add-on log.
- Before uninstalling, create a backup if you may need the SQLite history or
  generated configuration later. Removing the add-on also removes its
  Supervisor-managed runtime data.

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
- Home Assistant **Ingress** proxies the UI into the sidebar; the manifest
  publishes no host port (`ports: {}`), so `http://localhost:8377` is not a
  supported Home Assistant browser or HACS route
- The collector path subscribes only. MQTT Discovery publishes only when its
  two gates are enabled; topology performs the default delayed startup
  network-map request and can make further allowlisted requests when configured.
- Same codebase as the Docker Compose / dev path

## Security

The add-on dashboard is served through Home Assistant **Ingress** (admin-only
panel). Supervisor injects a validated user identity; ZigbeeLens Core trusts it
only from the exact Supervisor ingress peer (`172.30.32.2`) and rejects
non-ingress browser access. No API token is required for Ingress.

An API token does not create a network route. HACS pairing requires an actual
Core HTTP origin reachable from Home Assistant, and this repository does not
define a portable direct URL for the packaged add-on. Use the add-on's full
Ingress UI by itself, or use the documented standalone Docker + HACS route.
See [docs/security.md](../../../docs/security.md) and
[docs/hacs.md](../../../docs/hacs.md).

The source add-on runner can install the optional `security.api_token` as a
secret file. The current generated add-on repository instead references the
standalone image entrypoint, which does not install that option. Treat bearer
fallback in generated-repository installs as release-blocked until packaging
uses the add-on runner.

## Support

- Issues: https://github.com/theaussiepom/zigbeelens/issues
- Docs: [docs/addon-dev.md](../../../docs/addon-dev.md) (developers)
