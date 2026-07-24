# Configuration

This is the canonical reference for ZigbeeLens Core configuration. The owning
schema is `apps/core/src/zigbeelens/config/models.py`; environment overrides are
allowlisted in `apps/core/src/zigbeelens/config/loader.py`.

All Core configuration is loaded at process startup. Restart Core after changing
YAML, environment variables, or secret files.

## Choose the right configuration surface

| Deployment | Configuration owner | What you edit |
|------------|---------------------|---------------|
| Docker / Compose | ZigbeeLens Core | A YAML file mounted at `/config/config.yaml`, plus optional environment or secret-file overrides |
| Direct Core | ZigbeeLens Core | `config/config.yaml`, `ZIGBEELENS_CONFIG`, or `zigbeelens --config PATH` |
| Home Assistant add-on (deferred; not in the current HACS release) | Supervisor + source add-on launcher | Retained for non-regression validation only |
| HACS integration | Home Assistant config entry | Core URL, optional Core API token, TLS verification, panel visibility, and polling interval |

The HACS integration does not configure or install Core. It connects to an
already-running Core service.

## Minimal live Core configuration

Use obvious local placeholders and keep credentials out of committed YAML:

```yaml
server:
  host: 127.0.0.1
  port: 8377

mode:
  mock: false

security:
  mode: local

mqtt:
  server: mqtt://192.0.2.10:1883
  username: ""
  password: ""

networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt

storage:
  path: ./data/zigbeelens.sqlite
```

For Docker, use the maintained
[`deploy/docker/config.example.yaml`](../deploy/docker/config.example.yaml);
it binds `0.0.0.0` inside the container and stores SQLite under `/data`.

## Core settings

### Server and data mode

| Key | Type and default | Meaning |
|-----|------------------|---------|
| `server.host` | string, `127.0.0.1` | Listen address. Container examples explicitly use `0.0.0.0`. |
| `server.port` | integer `1..65535`, `8377` | Core API and bundled-UI port. |
| `mode.mock` | boolean, `true` | Development fixture mode. Supported deployment examples set this to `false`. |
| `mode.default_scenario` | string, development fixture ID | Default fixture in mock mode. This is a development/testing setting, not a normal published feature. |

### MQTT and networks

| Key | Type and default | Meaning |
|-----|------------------|---------|
| `mqtt.server` | string, `mqtt://mosquitto:1883` | Broker URI. `mqtts://` selects TLS and defaults to port 8883. |
| `mqtt.username` | string, empty | Optional broker username. Prefer `ZIGBEELENS_MQTT_USERNAME`. |
| `mqtt.password` | secret string, empty | Optional broker password. Prefer an environment or `*_FILE` source. |
| `mqtt.client_id` | string, `zigbeelens` | MQTT client ID prefix. The topology and Discovery publishers add their own suffixes. |
| `mqtt.tls.enabled` | boolean, `false` | Enable TLS even when the URI is not `mqtts://`. |
| `mqtt.tls.reject_unauthorized` | boolean, `true` | Verify the broker certificate. Disabling verification weakens transport security. |
| `networks` | list, empty | One entry per Zigbee2MQTT instance. A live deployment needs at least one useful entry. |
| `networks[].id` | required non-empty string | Stable stored identity and URL key. Do not rename it casually. IDs must be unique. |
| `networks[].name` | required string | Display label; it is not an identity key. |
| `networks[].base_topic` | required string | Exact Zigbee2MQTT base topic, without a trailing slash. |

Device identity is always `network_id` plus `ieee_address`; friendly names may
repeat across networks.

### Storage and retention

| Key | Type and default | Meaning |
|-----|------------------|---------|
| `storage.path` | string, `./data/zigbeelens.sqlite` | SQLite path. Docker uses `/data/zigbeelens.sqlite`; the add-on owns `/data/zigbeelens/zigbeelens.sqlite`. |
| `storage.retention_days` | integer `1..3650`, `7` | Telemetry-history retention, not report or incident retention. |
| `storage.resolved_incident_retention_days` | integer `1..3650` or `null`, `90` | Age limit for resolved incidents. `null` keeps them indefinitely. Open and watching incidents are not age-purged. |
| `storage.report_retention_days` | integer `1..3650` or `null`, `null` | Optional saved-report retention. `null` means until manually deleted. |
| `storage.maintenance_interval_hours` | integer `1..168`, `24` | Interval between Core-owned maintenance cycles. |

In Home Assistant add-on options only, `0` is the Supervisor sentinel for
indefinite resolved-incident retention or manual-only report retention. Do not
put `0` in Core YAML.

### Diagnostic thresholds

| Key | Type and default |
|-----|------------------|
| `diagnostics.incident_window_seconds` | integer `>=1`, `180` |
| `diagnostics.stale_after_hours` | integer `>=1`, `24` |
| `diagnostics.low_battery_percent` | integer `0..100`, `20` |
| `diagnostics.weak_link_threshold` | integer `0..255`, `40` |
| `diagnostics.flapping_threshold` | integer `>=1`, `3` |
| `diagnostics.recently_unstable_window_hours` | integer `>=1`, `24` |
| `diagnostics.bridge_stale_after_minutes` | integer `>=1`, `10` |
| `diagnostics.mains_stale_after_hours` | integer `>=1`, `12` |
| `diagnostics.battery_stale_after_hours` | integer `>=1`, `48` |
| `diagnostics.incident_watch_window_minutes` | integer `>=1`, `30` |
| `diagnostics.incident_resolution_grace_minutes` | integer `>=1`, `5` |
| `diagnostics.network_wide_device_percent` | integer `1..100`, `25` |
| `diagnostics.network_wide_min_devices` | integer `>=1`, `5` |
| `diagnostics.correlated_min_devices` | integer `>=2`, `2` |
| `diagnostics.stale_cluster_min_devices` | integer `>=1`, `3` |
| `diagnostics.low_battery_cluster_min_devices` | integer `>=1`, `3` |
| `diagnostics.interview_failure_min_devices` | integer `>=1`, `2` |

These thresholds classify stored observations. They do not prove a cause.
Missing source data remains unavailable or unknown rather than becoming a
measured zero.

### Feature gates

| Key | Type and default | Meaning |
|-----|------------------|---------|
| `features.mqtt_collector` | boolean, `true` | Run the live subscribe-only collector when `mode.mock` is false. |
| `features.mqtt_discovery` | boolean, `false` | First gate for the optional MQTT Discovery publisher. |
| `features.bridge_logs` | boolean, `true` | Ingest supported Zigbee2MQTT bridge log observations. |
| `features.device_payload_history` | boolean, `true` | Retain supported device-payload history. |
| `features.manual_network_map` | boolean, `false` | First gate for user-requested topology capture. |
| `features.automatic_network_map` | boolean, `false` | First gate for legacy interval-based automatic topology capture. |

MQTT Discovery runs only when both `features.mqtt_discovery` and
`mqtt_discovery.enabled` are true. Manual topology capture requires both
`features.manual_network_map` and `topology.manual_capture_enabled`.

### Topology

| Key | Type and default | Meaning |
|-----|------------------|---------|
| `topology.enabled` | boolean, `true` | Subscribe to network-map responses and retain topology evidence. |
| `topology.startup_scan` | boolean, `true` | Request one map per network after the collector and bridges are ready. |
| `topology.startup_stable_delay_seconds` | integer `>=0`, `60` | Stable-ready delay before startup requests. |
| `topology.refresh_interval_seconds` | integer `>=0`, `0` | Periodic request interval. `0` disables this periodic path. |
| `topology.manual_capture_enabled` | boolean, `false` | Second gate for confirmed UI/API capture. |
| `topology.automatic_capture_enabled` | boolean, `false` | Second gate for the legacy hours-based periodic path. |
| `topology.automatic_capture_interval_hours` | integer `>=1`, `24` | Used only when the automatic gates are enabled and `refresh_interval_seconds` is `0`. |
| `topology.max_snapshots_per_network` | integer `>=1`, `30` | Per-network terminal-snapshot count cap, independent of age retention. |
| `topology.capture_on_incident` | boolean, `false` | Reserved in the current schema; no incident-triggered capture path is implemented. Leave false. |
| `topology.warn_before_capture` | boolean, `true` | Reserved compatibility setting. The current manual UI/API confirmation is enforced independently. |

The startup scan is an allowlisted diagnostic publish to
`{base_topic}/bridge/request/networkmap`; it can create temporary mesh load.
Topology is capture-time evidence, not proof of a current route.

### MQTT Discovery

| Key | Type and default | Meaning |
|-----|------------------|---------|
| `mqtt_discovery.enabled` | boolean, `true` | Second Discovery gate; the feature gate is false by default. |
| `mqtt_discovery.topic_prefix` | string, `homeassistant` | Home Assistant discovery-config prefix. |
| `mqtt_discovery.state_topic_prefix` | string, `zigbeelens` | ZigbeeLens-owned state/availability prefix. |
| `mqtt_discovery.retain` | boolean, `true` | Controls retained state, attributes, and online/offline availability publications. Discovery configs/tombstones and the broker last will are always retained. |
| `mqtt_discovery.device_name` | string, `ZigbeeLens` | Home Assistant device label. |
| `mqtt_discovery.object_id_prefix` | string, `zigbeelens` | Accepted compatibility option. The current summary publisher ignores it and uses fixed `zigbeelens_<entity-key>` object IDs. |

Normal Discovery publishes are restricted by the topic validator and do not
target device-control paths. The broker last will is registered before that
validator; keep the default state prefix and see
[the safety audit](safety-audit.md#mqtt-discovery) for the current release
blocker. Changing `mqtt_discovery.object_id_prefix` currently has no runtime
effect; do not document or rely on custom object IDs until the publisher
consumes it.
Keep `mqtt_discovery.state_topic_prefix` at `zigbeelens` unless independently
reviewed: the broker last will is currently registered at `<prefix>/status`
before normal topic validation, so configuration loading does not catch an
overlap with a Zigbee2MQTT base topic.

### Reporting

| Key | Type and default | Meaning |
|-----|------------------|---------|
| `reporting.max_recent_events` | integer `>=1`, `100` | Maximum recent timeline rows considered for a report. |
| `reporting.max_metric_samples_per_device` | integer `>=1`, `50` | Accepted compatibility option; current report composition does not consume it. |
| `reporting.max_availability_changes_per_device` | integer `>=1`, `50` | Accepted compatibility option; current report composition does not consume it. |
| `reporting.include_raw_payloads` | boolean, `false` | Accepted and resolved, but exact-v3 composition has no raw-payload section and currently does not consume this value. Keep false. |
| `reporting.default_profile` | `standard`, `public_safe`, or `strict`; `standard` | Accepted configuration option. The current request model supplies `standard` before configuration fallback, so non-standard configured defaults are ineffective; select the profile explicitly per report request. |

The section name is `reporting`, not `reports`.
Treat `reporting.default_profile` as a release-blocked compatibility option
until an omitted request profile can reach the configured fallback (or the
option is removed). The two unused sample limits and `include_raw_payloads`
also require implementation or removal before they can be presented as
effective controls.

### Security

| Key | Type and default | Meaning |
|-----|------------------|---------|
| `security.mode` | `local`, `authenticated`, or `home_assistant_ingress`; `local` | Authentication posture. `authenticated` requires an API token. |
| `security.api_token` | secret string or `null`, `null` | Static Bearer credential, 32–4096 bearer-compatible ASCII characters. Prefer environment or file injection. |
| `security.session_secret` | secret string or `null`, `null` | Session-signing secret, at least 32 characters. Browser sessions require both secrets. |
| `security.session_ttl_seconds` | integer `300..604800`, `43200` | Fixed browser-session lifetime. |
| `security.session_cookie_secure` | boolean or `null`, `null` | Automatic when null: false on loopback and true otherwise. |
| `security.cors_allowed_origins` | list of exact origins, empty | Credentialed CORS and browser-session mutation Origin allowlist. |
| `security.frame_ancestor_origins` | list of exact origins, empty | External origins allowed to frame the bundled UI. Independent from CORS. |
| `security.ingress_trusted_proxies` | list of exact IP literals, empty | Immediate peers allowed to assert Supervisor ingress identity. |
| `security.ingress_proxy_only` | boolean, `false` | Restrict the browser UI to trusted ingress. Valid only in ingress mode. |

The add-on generates its ingress security block; users should not copy that
trusted-peer configuration into a normal Docker deployment. See
[Security](security.md) for the authentication, browser-session, Origin, CSRF,
and ingress contracts.

## Environment and secret overrides

Only these variables override typed Core configuration:

| Variable | Overrides |
|----------|-----------|
| `ZIGBEELENS_CONFIG` | Configuration file path |
| `ZIGBEELENS_PORT` | `server.port` |
| `ZIGBEELENS_SECURITY_MODE` | `security.mode` |
| `ZIGBEELENS_SECURITY_API_TOKEN` / `ZIGBEELENS_SECURITY_API_TOKEN_FILE` | `security.api_token` |
| `ZIGBEELENS_SECURITY_SESSION_SECRET` / `ZIGBEELENS_SECURITY_SESSION_SECRET_FILE` | `security.session_secret` |
| `ZIGBEELENS_MQTT_USERNAME` | `mqtt.username` |
| `ZIGBEELENS_MQTT_PASSWORD` / `ZIGBEELENS_MQTT_PASSWORD_FILE` | `mqtt.password` |
| `ZIGBEELENS_MOCK_SCENARIO` | `mode.default_scenario` (development/testing) |

For each secret, set the direct variable or its `_FILE` counterpart, never
both. `ZIGBEELENS_API_KEY` is a temporary configuration-source alias for the
API token and conflicts with the canonical API-token variables.

Runtime-only variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `ZIGBEELENS_LOG_LEVEL` | `INFO` | Python log level |
| `ZIGBEELENS_OPENAPI_ENABLED` | false | Enable `/docs`, `/redoc`, and `/openapi.json` |
| `ZIGBEELENS_STATIC_DIR` | packaged image path when set | Bundled UI asset directory |
| `TZ` | host/image default | Process timezone |

Never use `VITE_*` variables for secrets; those values are compiled into browser
assets.

## Home Assistant add-on ownership

The add-on is deferred and is not part of the current HACS release. This section
records its source configuration boundary for non-regression purposes; it is
not current installation guidance.

The source add-on exposes Supervisor options for MQTT, networks, storage,
diagnostics, reporting, feature gates, MQTT Discovery, topology, and an
optional `security.api_token`. It owns and does not expose these generated Core
values:

- `server.host: 0.0.0.0` and `server.port: 8377`;
- `mode.mock: false`;
- `security.mode: home_assistant_ingress`;
- the exact Supervisor trusted peer and `ingress_proxy_only: true`;
- `storage.path: /data/zigbeelens/zigbeelens.sqlite`.

The source add-on runner stores the optional API token in
`/data/zigbeelens/secrets/api_token`, not generated YAML. The current generated
add-on repository selects the standalone image entrypoint, which does not
install or export that token file; bearer fallback is therefore unavailable in
that packaged path until packaging is corrected. The token does not create a
HACS-reachable route.

The Supervisor schema also currently accepts `0` for the three
`reporting.max_*` options while Core requires values of at least `1`; do not use
zero. Add-on option changes require an add-on restart.

See the [add-on README](../apps/addon/zigbeelens/README.md) for its option names,
sentinel values, backup path, logs, and ingress behavior.

## HACS integration settings

These are Home Assistant integration settings, not Core configuration:

| Key | Default | Where changed |
|-----|---------|---------------|
| `core_url` | `http://localhost:8377` | Initial setup or Reconfigure; replace the default with an address actually reachable from Home Assistant |
| `api_token` | empty | Initial setup, Reconfigure, or Reauthenticate |
| `verify_ssl` | `false` | Initial setup or Reconfigure |
| `panel_enabled` | `true` | Initial setup or Configure |
| `scan_interval` | `60` seconds; Configure accepts `15..900` | Configure |

The OptionsFlow returns both selected values in its result. Home Assistant
persists them and the registered update listener performs one effective reload;
the recreated coordinator uses the selected interval. The enrichment manager's
forced 15-minute reconciliation is separate from this configurable coordinator
poll.

The integration never installs Core and does not inherit the add-on token
automatically.

The server-side integration reads Core health/diagnostic, configuration status,
Decision Dashboard, capabilities, and bounded `/api/v1/devices` inventory.
Its only write is the strict complete Home Assistant enrichment snapshot to
Core-local storage, with an exact clear allowed on explicit config-entry
removal. HA names and areas supplement—not replace—the Core/Zigbee2MQTT
friendly name. Matching resolves to exact `(network_id, ieee_address)` and
fails closed on ambiguity; unavailable source/inventory or transient failure
retains the prior accepted snapshot, while an accepted complete-empty snapshot
clears it.

The reviewed compatibility lanes are exact Home Assistant `2025.1.0` on Python
`3.12` and Home Assistant `2026.7.3` on Python `3.14`.

## Validate a configuration

From the repository root with Core development dependencies installed:

```bash
cd apps/core
uv run python -c \
  'from zigbeelens.config import load_effective_config; load_effective_config("../../deploy/docker/config.example.yaml"); print("configuration valid")'
```

Validate all maintained deployment/package examples with:

```bash
ZIGBEELENS_REQUIRE_DOCKER_COMPOSE=1 ./scripts/validate-compose.sh
./scripts/validate-addon.sh
./scripts/validate-ha-integration.sh
```

Related references:

- [Docker install](docker.md)
- [Home Assistant add-on](../apps/addon/zigbeelens/README.md)
- [HACS integration](hacs.md)
- [Security](security.md)
- [Topology snapshots](topology.md)
- [MQTT Discovery](mqtt-discovery.md)
- [Reports](reports.md)
