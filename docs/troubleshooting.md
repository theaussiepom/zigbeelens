# Troubleshooting

Common ZigbeeLens issues and fixes.

## No devices showing

1. Confirm Zigbee2MQTT is running and publishing to MQTT.
2. Check `networks[].base_topic` matches Zigbee2MQTT exactly (case-sensitive).
3. Verify Core is in **live mode** (`mode.mock: false`).
4. Check `/api/health` — collector should show connected.
5. Wait for retained messages on first connect — large networks may take a minute.

## Wrong Zigbee2MQTT base topic

Symptoms: empty devices, bridge state unknown, no events.

Fix: edit config so `networks[].base_topic` matches Zigbee2MQTT `base_topic` setting. Restart Core.

Multi-network: each Zigbee2MQTT instance needs its own `networks[]` entry with a unique stable `id`.

## MQTT authentication failure

Symptoms: collector disconnected, `/api/health` shows MQTT error.

Fix:

- Verify `mqtt.server`, `mqtt.username`, `mqtt.password`
- Test with `mosquitto_sub` from the same host
- Check broker ACLs allow subscribe to `{base_topic}/#`

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
- ZigbeeLens shows "unknown" when data has not arrived — this is expected

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
- Check the report `redaction` status block for field counts
- Narrow scope (single device/incident) for more detail

See [redaction.md](redaction.md).

## HACS integration cannot connect

1. Confirm ZigbeeLens Core is running (add-on or Docker).
2. Use correct Core URL:
   - HAOS add-on: `http://localhost:8377` (typical)
   - Docker on another host: `http://<host>:8377`
3. Check firewall from HA to Core.
4. If Core requires bearer authentication, set the same Core API token in the
   HACS config flow / reauth form (leave blank only for trusted-open Core).
5. When Home Assistant prompts to reauthenticate ZigbeeLens, enter the current
   token or leave blank if Core returned to trusted-open mode.
6. Review HA logs for connection errors (never expect the token in logs).

See [hacs.md](hacs.md).

## Add-on Ingress blank page

1. Confirm add-on is started and healthy.
2. Check add-on log for Core startup errors.
3. Verify MQTT config in add-on options.
4. Try direct access on port 8377 if exposed for debugging.
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

- SSE requires proxy buffering disabled for `/api/events/stream`
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
3. Check `/api/health` for discovery status.
4. Discovery publishes summary entities only — not every Zigbee device.

See [mqtt-discovery.md](mqtt-discovery.md).

## Topology capture disabled

Topology is **enabled by default** with one startup scan after collector and bridge readiness. To disable entirely:

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
- Only one capture at a time per network
- Check Core logs for timeout or parse errors

## HA enrichment not matching devices

- Enrichment requires POST to `/api/enrichment/homeassistant`
- IEEE address match is high confidence; friendly name match is medium
- Duplicate friendly names reduce match quality
- HACS auto-push is not wired in v0.1.0 — manual API or future integration update

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
| HACS 401 against add-on Core | Optional bearer fallback not configured | Set the same token in add-on `security.api_token` and HACS credential (never in URLs) |
| Warning: non-loopback bind with `mode=local` and no API token | Remotely reachable Core in trusted-open mode | Bind loopback, restrict network access, or configure an API token for bearer auth |

Config validation errors intentionally omit rejected secret values. See [security.md](security.md).

## Still stuck?

1. Generate a `public_safe` report from the Reports page
2. Open an issue using the [diagnostic report template](../.github/ISSUE_TEMPLATE/diagnostic_report.yml)
3. Include Zigbee2MQTT version, install path, and symptom description

Do **not** paste secrets or raw MQTT payloads.
