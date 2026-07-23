# Troubleshooting

Common ZigbeeLens issues and fixes.

## No devices showing

1. Confirm Zigbee2MQTT is running and publishing to MQTT.
2. Check `networks[].base_topic` matches Zigbee2MQTT exactly (case-sensitive).
3. Verify Core is in **live mode** (`mode.mock: false`).
4. Check `/api/v1/health` — collector should show connected.
5. Wait for retained messages on first connect — large networks may take a minute.

## Wrong Zigbee2MQTT base topic

Symptoms: empty devices, bridge state unknown, no events.

Fix: edit config so `networks[].base_topic` matches Zigbee2MQTT `base_topic` setting. Restart Core.

Multi-network: each Zigbee2MQTT instance needs its own `networks[]` entry with a unique stable `id`.

## MQTT authentication failure

Symptoms: collector disconnected, `/api/v1/health` shows MQTT error.

Fix:

- Verify `mqtt.server`, `mqtt.username`, `mqtt.password`
- Test with `mosquitto_sub` from the same host
- Check broker ACLs allow the [documented collector subscriptions](safety-audit.md#mqtt-collector)
- If topology is enabled, allow the one diagnostic publish to
  `{base_topic}/bridge/request/networkmap` and the response subscription
- If MQTT Discovery is enabled, allow its configured ZigbeeLens-owned publish
  prefixes separately

## Collector disconnected

1. Check broker reachability and credentials.
2. Review Core logs for connection errors.
3. Firewalls between Docker and broker — use host IP not `localhost` from inside containers.
4. MQTT over TLS: ensure URI scheme and certificates are correct.

## Bridge state unknown

- Zigbee2MQTT may not have published bridge state yet
- Wrong `base_topic`
- Collector not connected
- Bridge offline in Zigbee2MQTT

Check Zigbee2MQTT logs and `zigbee2mqtt/bridge/state` topic manually.

## Availability missing

Zigbee2MQTT **availability** must be enabled for online/offline tracking:

```yaml
# Zigbee2MQTT configuration.yaml
availability: true
```

Some devices never report availability by design (sleepy end devices).

## LQI or battery missing

- Not all devices report link quality or battery via MQTT
- Reporting intervals vary by device and configuration
- ZigbeeLens shows "unknown" when data has not arrived. Unknown is not a
  measured zero and does not establish that the device is healthy.

## Duplicate friendly names

Friendly names are **not globally unique** across networks. ZigbeeLens identifies devices by `network_id` + `ieee_address`.

If two devices share a name within one network, use IEEE address in the UI and reports.

## Incidents not appearing

- Thresholds in `diagnostics.*` may not be met yet
- Insufficient telemetry — check device last-seen times
- Mock mode — switch to live or select a scenario with incidents
- Recent instability may still be in "watching" state

## Reports redaction looks too aggressive

- Try `standard` instead of `public_safe` or `strict` for local use
- Check the report `redaction` status block for the profile and treatment modes
- Narrow scope (single device/incident) for more detail

See [redaction.md](redaction.md).

## HACS integration cannot connect

1. Confirm a standalone or otherwise Home-Assistant-reachable ZigbeeLens Core
   service is running. The packaged add-on has no portable HACS backend origin.
2. Use a Core URL that is reachable from the Home Assistant Core runtime, for
   example `http://<zigbeelens-core-host>:8377` for a standalone/Compose
   deployment. The add-on publishes no host port: its UI is reached through
   Home Assistant Ingress, and `http://localhost:8377` is not a portable
   HACS-to-add-on Core address.
3. Check firewall from HA to Core.
4. If Core requires bearer authentication, set the same Core API token in the
   HACS config flow / reauth form (leave blank only for trusted-open Core).
5. When Home Assistant prompts to reauthenticate ZigbeeLens, enter the current
   token or leave blank if Core returned to trusted-open mode.
6. Review HA logs for connection errors (never expect the token in logs).

See [hacs.md](hacs.md).

## Add-on Ingress blank page during scoped testing

This section applies to source-built/local pre-release testing now, or to a
future published add-on artifact after publication gates close. The generated
image-based repository remains publication-blocked and is not a supported
release installation.

1. Confirm the scoped local or future-published add-on is started and healthy.
2. Check add-on log for Core startup errors.
3. Verify MQTT config in add-on options.
4. Open ZigbeeLens through the Home Assistant sidebar Ingress route; the
   packaged manifest exposes no direct host port.
5. Clear browser cache — static UI is bundled with Core.

See [addon-dev.md](addon-dev.md).

## Docker database permission issue

Symptoms: Core fails to start, SQLite permission errors.

```bash
sudo chown -R 1000:1000 data
```

Ensure `/data` volume is writable by container user `zigbeelens` (UID 1000).

See [docker.md](docker.md).

## Reverse proxy / SSE issue

Symptoms: dashboard stale, live indicator stuck.

- SSE requires proxy buffering disabled for `/api/v1/events/stream` (the
  `/api/events/stream` alias remains compatible)
- nginx example: `proxy_buffering off;` for the stream location
- UI falls back to polling if SSE fails — may be slower

## MQTT Discovery entities not appearing

Both flags required:

```yaml
features:
  mqtt_discovery: true
mqtt_discovery:
  enabled: true
```

1. Restart Core after config change.
2. Confirm HA MQTT integration is connected to the same broker.
3. Check `/api/v1/health` for discovery status.
4. Discovery publishes summary entities only — not every Zigbee device.

See [mqtt-discovery.md](mqtt-discovery.md).

## Topology capture disabled

Topology is **enabled by default**. In live mode, its startup scan waits for
collector and bridge readiness. To disable entirely:

```yaml
topology:
  enabled: false
```

To keep topology enabled but skip the startup scan:

```yaml
topology:
  enabled: true
  startup_scan: false
```

Manual capture still requires explicit confirmation:

```yaml
features:
  manual_network_map: true
topology:
  manual_capture_enabled: true
```

Capture requires explicit confirmation in the UI or `confirmed: true` in the API.

See [topology.md](topology.md).

## Topology capture slow or unavailable

- Large networks may take 30+ seconds
- Zigbee2MQTT must support network map requests
- Only one capture can be pending in a Core process at a time
- Check Core logs for timeout or parse errors

If a capture completes with no usable node/link layout, keep the result as
limited evidence. Do not interpret zero displayed topology counts as proof that
the network has no links.

## HA enrichment not matching devices

- Enrichment requires POST to `/api/v1/enrichment/homeassistant` (or the
  compatible `/api` alias)
- IEEE address match is high confidence; friendly name match is medium
- Duplicate friendly names reduce match quality
- The current HACS integration does not push registry enrichment automatically;
  use a reviewed client/manual integration if this optional Core-local metadata
  is needed

## Storage maintenance failed

Symptoms: Settings shows a last maintenance error; `/api/v1/storage/status` has `maintenance.last_error_code` / `failure_category`; logs mention storage maintenance.

| `last_error_code` | Meaning | What to do |
|-------------------|---------|------------|
| `database_busy` | SQLite locked / busy during a batch | Normal under load; committed batches are kept, `more_work_pending` may be true. Wait for the next scheduled cycle or retry when quieter. Avoid concurrent `--apply` against a live Core process. |
| `integrity_check_failed` | Preflight or post-cycle foreign-key/integrity gate failed | Do **not** force purge. Run `zigbeelens storage check --database <path>` (optionally `--full`). Restore from a known-good backup if checks fail. See [backups.md](backups.md). |
| `maintenance_failed` | Unexpected error mid-cycle | Check Core logs. Partial deletes from earlier batches may already be committed; re-run after the cause is fixed. |
| `interrupted` | Process stopped while `running: true` | Cleared/marked on next Core start; next cycle continues safely. |
| `schema_mismatch` / `schema_too_old` (CLI) | Maintenance CLI opened a DB that is not at the current schema | Start Core so migrations run (including `012`), then retry. CLI `--apply` never migrates. |

Also remember:

- `check` and `maintenance --dry-run` are truly non-mutating
- Invalid/future timestamps are retained (counted as warnings), not deleted
- Active in-memory topology captures are excluded from periodic maintenance
- Track 6 does not run automatic `VACUUM`

## Storage integrity check failed at startup

Symptoms: Core refuses to start destructive services; logs show storage integrity failure.

1. Stop Core or the scoped source-built/local pre-release add-on (or future
   published artifact).
2. Keep the current DB as a rollback copy.
3. Run `zigbeelens storage check --database /path/to/zigbeelens.sqlite` (add `--full` for a deeper check).
4. If checks fail, restore a verified backup (online `storage backup` snapshot,
   or an HA backup for the scoped add-on paths above), then start Core so
   migrations + integrity + maintenance run in order.
5. Confirm `/api/v1/storage/status` integrity facts show `status: ok` after a healthy start.

## Security configuration errors

| Symptom / log | Likely cause | Fix |
|---------------|--------------|-----|
| `Conflicting secret sources: both … and …_FILE` | Direct env var and `*_FILE` both set | Keep only one source |
| `Conflicting API token sources` | `ZIGBEELENS_API_KEY` combined with canonical token vars | Use either the legacy alias **or** `ZIGBEELENS_SECURITY_API_TOKEN` / `_FILE` |
| `Secret file not found` / `not a regular readable file` | Missing path, directory, or permission issue | Point `*_FILE` at a readable regular file |
| `Secret file is empty` | File contains only newlines/whitespace after CR/LF strip | Put a non-empty secret in the file |
| `must be at least 32 characters` | Token/session secret too short | Generate a longer secret (`openssl rand -base64 48`) |
| `api_token is required when mode is authenticated` | `security.mode=authenticated` without token | Set `ZIGBEELENS_SECURITY_API_TOKEN` or `_FILE` |
| `ingress_trusted_proxies is required when mode is home_assistant_ingress` | Ingress mode without exact peer list | Add exact IP literals (add-on sets `172.30.32.2`) |
| UI: “Open ZigbeeLens through Home Assistant” | Direct URL to add-on Core outside ingress | Open the ZigbeeLens add-on panel from Home Assistant |
| HACS 401 against protected standalone Core | Bearer credential missing or stale | Set the same Core `security.api_token` in the HACS credential (never in URLs) |
| Warning: non-loopback bind with `mode=local` and no API token | Remotely reachable Core in trusted-open mode | Bind loopback, restrict network access, or configure an API token for bearer auth |

Config validation errors intentionally omit rejected secret values. See [security.md](security.md).

## Still stuck?

1. Generate a contextual `public_safe` report from the affected Device,
   Incident, Network, or Mesh surface, or a full report from Reports
2. Open an issue using the [diagnostic report template](../.github/ISSUE_TEMPLATE/diagnostic_report.yml)
3. Include Zigbee2MQTT version, install path, and symptom description

Do **not** paste secrets or raw MQTT payloads.
