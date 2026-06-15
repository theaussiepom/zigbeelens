# Pre-release smoke test — deployed GHCR image + HACS integration

Use this guide to validate the **real** install path before tagging `v0.1.0`.

| Item | Value |
|------|-------|
| GitHub owner | `theaussiepom` |
| Main repo | https://github.com/theaussiepom/zigbeelens |
| HACS repo | https://github.com/theaussiepom/zigbeelens-hacs |
| Add-on repo | https://github.com/theaussiepom/zigbeelens-addons |
| GHCR image | `ghcr.io/theaussiepom/zigbeelens` |
| Pre-release tag | **`edge`** (from `main`; not `v0.1.0` yet) |

## Pre-flight checklist

Before you start, confirm:

- [ ] Docker is running locally
- [ ] You can reach your MQTT broker from the Docker host (host IP, not `localhost` inside container unless broker is on host network)
- [ ] Zigbee2MQTT is running and publishing for both configured base topics
- [ ] Base topics in config match your broker (defaults below are common; yours may differ — e.g. `home` / `home2` instead of `zigbee2mqtt` / `zigbee2mqtt-home2`). Verify with `mosquitto_sub -t '# -v'` or your broker UI before configuring networks.
- [ ] You have MQTT credentials ready (do **not** commit them)
- [ ] Port **8377** is free on the Docker host
- [ ] GHCR image is public: `docker pull ghcr.io/theaussiepom/zigbeelens:edge`
- [ ] Home Assistant can reach the Docker host IP on port 8377 (for HACS test)
- [ ] HACS is installed in Home Assistant

## Security acknowledgement (v0.1.0)

Before release testing, confirm you understand:

- ZigbeeLens Core has **no built-in authentication** in v0.1.0
- ZigbeeLens is **read-only for Zigbee control** (no permit join, remove, reset, bind/unbind, OTA, or channel changes)
- Some Core API routes modify **ZigbeeLens local data only** (reports, topology snapshots, HA enrichment)
- If Core is reachable beyond users or networks you trust, **access-control decisions are your responsibility**
- **HTTPS is not authentication** — it may be needed for optional HACS embedded view only

See [security.md](security.md).

Optional helper (creates dirs, copies template, refuses placeholder config):

```bash
./scripts/local-release-test.sh
```

---

## 1. Local config (two networks)

Create a **local-only** config. Never commit real credentials.

**Template (committed):** `local/zigbeelens-test/config/config.yaml.example`

**Your live config (gitignored):** `local/zigbeelens-test/config/config.yaml`

```bash
mkdir -p local/zigbeelens-test/config local/zigbeelens-test/data
cp local/zigbeelens-test/config/config.yaml.example local/zigbeelens-test/config/config.yaml
# Edit config.yaml — replace <your-mqtt-host>, <mqtt-user>, <mqtt-password>
```

Or paste directly (replace placeholders before saving):

```bash
mkdir -p local/zigbeelens-test/config local/zigbeelens-test/data

cat > local/zigbeelens-test/config/config.yaml <<'EOF'
server:
  host: 0.0.0.0
  port: 8377

mode:
  mock: false

mqtt:
  server: mqtt://<your-mqtt-host>:1883
  username: "<mqtt-user>"
  password: "<mqtt-password>"
  client_id: zigbeelens
  tls:
    enabled: false
    reject_unauthorized: true

networks:
  - id: home
    name: Home
    base_topic: zigbee2mqtt

  - id: home2
    name: Home 2
    base_topic: zigbee2mqtt-home2

storage:
  path: /data/zigbeelens.sqlite
  retention_days: 7

features:
  mqtt_collector: true
  mqtt_discovery: false
  bridge_logs: true
  device_payload_history: true
  manual_network_map: false
  automatic_network_map: false

topology:
  enabled: false
  manual_capture_enabled: false
  automatic_capture_enabled: false
  capture_on_incident: false
EOF
```

---

## 2. Pull and run published container

```bash
docker pull ghcr.io/theaussiepom/zigbeelens:edge

docker run --rm \
  --name zigbeelens \
  -p 8377:8377 \
  -v "$PWD/local/zigbeelens-test/config:/config:ro" \
  -v "$PWD/local/zigbeelens-test/data:/data" \
  ghcr.io/theaussiepom/zigbeelens:edge
```

If you used `zigbeelens-test/` at repo root instead of `local/zigbeelens-test/`, adjust the volume paths accordingly (both paths are gitignored).

### Verify API

```bash
curl -s http://localhost:8377/api/health | python3 -m json.tool
curl -s http://localhost:8377/api/config/status | python3 -m json.tool
curl -s http://localhost:8377/api/dashboard | python3 -m json.tool | head -40
curl -s http://localhost:8377/api/networks | python3 -m json.tool
```

Generate a redacted report (JSON):

```bash
curl -s -X POST http://localhost:8377/api/reports \
  -H "Content-Type: application/json" \
  -d '{"scope":"full","format":"json","redaction":{"profile":"public_safe"}}' \
  | python3 -m json.tool
```

Download the stored report (replace `<report-id>`):

```bash
curl -s "http://localhost:8377/api/reports/<report-id>/download" -o report.json
grep -iE 'password|network_key|secret' report.json || echo "No obvious secret keys in report"
```

Open the dashboard: **http://localhost:8377**

---

## 3. Container smoke checklist

- [ ] Image pulls from GHCR (`:edge`)
- [ ] Container starts without crash loop
- [ ] `/api/health` returns `"status": "ok"` (or equivalent healthy payload)
- [ ] UI loads at `/`
- [ ] Static assets load (no blank page / 404 on JS/CSS)
- [ ] SQLite database created under mounted `/data` (`zigbeelens.sqlite`)
- [ ] MQTT collector connects (`collector.connected: true` in `/api/health`)
- [ ] Both configured networks appear (`home`, `home2`)
- [ ] Devices appear for each network
- [ ] Health classifications appear on Overview / Devices
- [ ] Incidents appear only if real conditions warrant (empty is OK)
- [ ] Settings page shows collector status and both networks
- [ ] Reports page generates **JSON**
- [ ] Reports page generates **YAML**
- [ ] Reports page generates **Markdown**
- [ ] `public_safe` report redacts names/IEEE/host/IP as expected (API example below)
- [ ] No MQTT password in downloaded report
- [ ] No `network_key` in downloaded report
- [ ] Container logs do not show MQTT password (`docker logs zigbeelens`)

---

## 4. Install HACS integration

1. **HACS → Integrations → Custom repositories**
2. Repository URL: **https://github.com/theaussiepom/zigbeelens-hacs**
3. Category: **Integration**
4. Install **ZigbeeLens**
5. Restart Home Assistant if prompted
6. **Settings → Devices & services → Add Integration → ZigbeeLens**
7. Enter Core URL (see below)
8. Keep the companion panel enabled (default)

### Core URL examples

Use a URL **reachable from Home Assistant**, not only from your browser.

| Scenario | Core URL |
|----------|----------|
| HA on another machine, ZigbeeLens on Docker host | `http://<docker-host-lan-ip>:8377` |
| HA and ZigbeeLens on same Docker Compose network | `http://zigbeelens:8377` |
| HA container, ZigbeeLens on host Docker | `http://<host-lan-ip>:8377` |
| HAOS add-on (later) | `http://localhost:8377` only if Core is reachable inside HA namespace |

Do **not** use `http://localhost:8377` unless Home Assistant and ZigbeeLens share the same network namespace.

### HACS smoke checklist

- [ ] Custom repository added: https://github.com/theaussiepom/zigbeelens-hacs
- [ ] Integration installs without errors
- [ ] Restart completed if required
- [ ] Config flow accepts Core URL
- [ ] `sensor.zigbeelens_overall_health` appears
- [ ] `binary_sensor.zigbeelens_active_incident` appears
- [ ] Device count / unavailable / router risk sensors appear
- [ ] Per-network sensors appear (`Home`, `Home 2`)
- [ ] Sidebar **ZigbeeLens** entry appears
- [ ] Native companion panel loads
- [ ] Open Full Dashboard opens Core in a new tab
- [ ] Native companion panel loads with HTTP Core URL
- [ ] Open Full Dashboard opens Core in a new tab
- [ ] Try Embedded View shows a friendly explanation if Home Assistant is HTTPS and Core is HTTP
- [ ] Settings → Devices & services → ZigbeeLens → Configure can change Core URL without delete/re-add
- [ ] If using an HTTPS Core URL, Try Embedded View displays the full dashboard inside Home Assistant
- [ ] *(Optional advanced)* Caddy HTTPS stack from [hacs-embedded-view.md](hacs-embedded-view.md): Core URL updated, cert trusted, embedded view works
- [ ] Core connected state appears
- [ ] Overall health appears
- [ ] Active incident count appears
- [ ] Network count appears
- [ ] Device count appears
- [ ] Per-network summaries appear (`Home`, `Home 2`)
- [ ] **Open Full Dashboard** button opens `http://192.168.100.5:8377` in a new tab
- [ ] **Copy Core URL** works
- [ ] Stop Core → panel shows a calm disconnected state (no traceback)
- [ ] Stop Core → "Core unreachable" repair appears
- [ ] Start Core → panel recovers and repair clears
- [ ] Diagnostics download is redacted (no secrets)

### Switch Core URL from HTTP to HTTPS (embedded view test)

1. Put ZigbeeLens behind HTTPS (for Beast: `deploy/docker/docker-compose.beast-traefik.example.yaml` + Traefik headers middleware).
2. In Home Assistant: **Settings → Devices & services → ZigbeeLens → Configure**.
3. Change Core URL to the HTTPS address (for example `https://zigbeelens.theaussiepom.me`).
4. Confirm validation succeeds (`GET /api/health`).
5. Open the ZigbeeLens sidebar — native companion panel loads.
6. **Open Full Dashboard** opens the HTTPS URL in a new tab.
7. **Try Embedded View** — full dashboard renders inside Home Assistant.
8. **Back to Summary** works from embedded/blocked views.

### Companion panel notes

- The **Core dashboard is canonical** — HACS does not build a second dashboard or drill-down pages.
- The companion panel is a **status/launcher surface**: it renders a redacted summary supplied by the integration over the HA websocket, so the browser never fetches Core directly.
- This works whether Core is HTTP or HTTPS, and needs **no reverse proxy**.
- The default HACS view is a native companion panel over the HA websocket. **Open Full Dashboard** opens Core in a new tab. **Try Embedded View** is optional and only works when browser security allows embedding.
- The **Open Full Dashboard** button opens `http://<docker-host-ip>:8377` in a new tab — that URL must be reachable from your browser.
- Optional HTTPS reverse proxy for embedded view: [hacs-embedded-view.md](hacs-embedded-view.md)

---

## 5. Safety checks (pre-release)

- [ ] MQTT Discovery **disabled** in config (`features.mqtt_discovery: false`)
- [ ] Topology **disabled** in config
- [ ] `/api/health` shows subscribe-only collector (no publish to Zigbee2MQTT topics)
- [ ] Reports redacted before download
- [ ] No permit join / remove / reset controls in UI
- [ ] **No Scenario selector** in the header (it is dev-only; the published image builds without `VITE_ENABLE_SCENARIOS`)

> The Scenario (mock fixture) selector appears only on the Vite dev server, or in a build explicitly opted in with `VITE_ENABLE_SCENARIOS=true pnpm --filter @zigbeelens/ui build`. The published image never sets it.

---

## 6. After code fixes

If you fix issues in the monorepo:

1. Push to `main`
2. Wait for CI + Docker workflow (publishes new `:edge`)
3. `docker pull ghcr.io/theaussiepom/zigbeelens:edge`
4. Re-run this checklist

Re-sync HACS repo if integration source changed:

```bash
./scripts/package-hacs-repo.sh
cd dist/zigbeelens-hacs && git add -A && git commit -m "Sync from monorepo" && git push
```

---

## 7. Add-on repo (later)

HAOS add-on store: https://github.com/theaussiepom/zigbeelens-addons

Uses GHCR image `ghcr.io/theaussiepom/zigbeelens`. Add-on version `0.1.0` pulls `:0.1.0` once that tag exists; use `:edge` via standalone Docker for pre-release testing.

---

## Related

- [Docker install](docker.md)
- [HACS integration](hacs.md)
- [Release infrastructure](release-infra.md)
- [Troubleshooting](troubleshooting.md)
