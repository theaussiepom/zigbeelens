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

## Security acknowledgement

Before release testing, confirm you understand:

- Core may require `Authorization: Bearer` for protected API routes when an API token is configured
- Optional browser sessions need both API token and session secret; cookie mutations need exact `Origin` and `X-ZigbeeLens-CSRF-Token`
- The bundled UI uses session login when both are configured; bearer-only Core shows a UI setup-required state
- Add-on ingress identity: open UI through HA panel without API token; SSE and report download work; spoofed identity from another peer fails; optional bearer token enables HACS/direct API
- Diagnostics/logs contain neither API token nor Home Assistant user ID
- ZigbeeLens is **read-only for Zigbee control** (no permit join, remove, reset, bind/unbind, OTA, or channel changes)
- Some Core API routes modify **ZigbeeLens local data only** (reports, topology snapshots, HA enrichment)
- If Core is reachable beyond users or networks you trust, **access-control decisions are your responsibility**
- **HTTPS is not authentication** — it may be needed for optional HACS embedded view only

See [security.md](security.md).

Choose **one** release-test mode before `docker run`. Host environment variables are **not** inherited by the container unless you pass `-e` (or mount a token file).

### A. Token-enabled release test (bearer auth on)

Generate a fresh token on the host (do **not** commit it):

```bash
export ZIGBEELENS_TEST_API_TOKEN="$(openssl rand -base64 48)"
```

Pass it into the container with `-e ZIGBEELENS_SECURITY_API_TOKEN=...` (see §2). Host environment variables are **not** inherited unless you pass `-e`. After the container is up:

```bash
# Public readiness remains open
curl -s http://localhost:8377/healthz | python3 -m json.tool

# Expect HTTP 401 without Authorization
code=$(curl -s -o /tmp/zl-report-noauth.json -w '%{http_code}' -X POST http://localhost:8377/api/reports \
  -H "Content-Type: application/json" \
  -d '{"scope":"full","format":"json","redaction":{"profile":"public_safe"}}')
echo "without bearer: HTTP $code"
test "$code" = "401"

# Expect success with Bearer
code=$(curl -s -o /tmp/zl-report-auth.json -w '%{http_code}' -X POST http://localhost:8377/api/reports \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ZIGBEELENS_TEST_API_TOKEN" \
  -d '{"scope":"full","format":"json","redaction":{"profile":"public_safe"}}')
echo "with bearer: HTTP $code"
test "$code" = "200"
python3 -m json.tool < /tmp/zl-report-auth.json | head -40
```

(`*_FILE` alternative: write the token to a host file, mount it read-only, set `ZIGBEELENS_SECURITY_API_TOKEN_FILE` to the **container** path, and still use the host token value in the curl header.)

Optional browser-session check (requires `ZIGBEELENS_SECURITY_SESSION_SECRET` in the container as well):

```bash
curl -s -c /tmp/zl-cookies.txt -X POST http://localhost:8377/api/auth/session \
  -H "Authorization: Bearer $ZIGBEELENS_TEST_API_TOKEN" \
  | python3 -m json.tool
curl -s -b /tmp/zl-cookies.txt http://localhost:8377/api/dashboard | python3 -c 'import json,sys; json.load(sys.stdin); print("session cookie ok")'
CSRF=$(curl -s -b /tmp/zl-cookies.txt http://localhost:8377/api/auth/session | python3 -c 'import json,sys; print(json.load(sys.stdin)["csrf_token"])')
curl -s -b /tmp/zl-cookies.txt -X DELETE http://localhost:8377/api/auth/session \
  -H "Origin: http://localhost:8377" \
  -H "X-ZigbeeLens-CSRF-Token: $CSRF" -w 'logout HTTP %{http_code}\n' -o /dev/null
```


### B. No-token release test (trusted-open; API routes intentionally open)

Omit `ZIGBEELENS_SECURITY_API_TOKEN` / `_FILE` from `docker run`. In that configuration, protected API routes remain open — use only on a trusted local host. For token-enabled UI testing, also set `session_secret` so the standalone UI can create a browser session. For HACS against protected Core, configure the same API token in the integration (server-side bearer only).

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
  # resolved_incident_retention_days: 90   # null/omit = keep indefinitely
  # report_retention_days: null            # until manually deleted (default)
  # maintenance_interval_hours: 24

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
```

**A. Token-enabled** (requires `ZIGBEELENS_TEST_API_TOKEN` from the security section above):

```bash
docker run --rm \
  --name zigbeelens \
  -p 8377:8377 \
  -e ZIGBEELENS_SECURITY_API_TOKEN="$ZIGBEELENS_TEST_API_TOKEN" \
  -v "$PWD/local/zigbeelens-test/config:/config:ro" \
  -v "$PWD/local/zigbeelens-test/data:/data" \
  ghcr.io/theaussiepom/zigbeelens:edge
```

**B. No-token** (mutating routes intentionally open):

```bash
docker run --rm \
  --name zigbeelens \
  -p 8377:8377 \
  -v "$PWD/local/zigbeelens-test/config:/config:ro" \
  -v "$PWD/local/zigbeelens-test/data:/data" \
  ghcr.io/theaussiepom/zigbeelens:edge
```

If you used `zigbeelens-test/` at repo root instead of `local/zigbeelens-test/`, adjust the volume paths accordingly (both paths are gitignored).

### Verify API

`healthz` and version are public. In token-enabled mode, all other API reads below need Bearer. Never put the token in the URL.

```bash
AUTH_ARGS=()
if [[ -n "${ZIGBEELENS_TEST_API_TOKEN:-}" ]]; then
  AUTH_ARGS=(-H "Authorization: Bearer $ZIGBEELENS_TEST_API_TOKEN")
fi

curl -s http://localhost:8377/healthz | python3 -m json.tool
curl -s http://localhost:8377/api/version | python3 -m json.tool
curl -s "${AUTH_ARGS[@]}" http://localhost:8377/api/health | python3 -m json.tool
curl -s "${AUTH_ARGS[@]}" http://localhost:8377/api/capabilities | python3 -m json.tool
curl -s "${AUTH_ARGS[@]}" http://localhost:8377/api/dashboard | python3 -c 'import json,sys; d=json.load(sys.stdin); assert isinstance(d.get("investigation_priorities"), list); assert isinstance(d.get("data_coverage_warnings"), list); print("dashboard decision surfaces ok")'
curl -s "${AUTH_ARGS[@]}" http://localhost:8377/api/config/status | python3 -m json.tool
curl -s "${AUTH_ARGS[@]}" http://localhost:8377/api/dashboard | python3 -m json.tool | head -40
curl -s "${AUTH_ARGS[@]}" http://localhost:8377/api/networks | python3 -m json.tool
```

Generate a redacted report (JSON).

**A. Token-enabled** — include Bearer (and run the 401 / success checks from the security section):

```bash
curl -s -X POST http://localhost:8377/api/reports \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ZIGBEELENS_TEST_API_TOKEN" \
  -d '{"scope":"full","format":"json","redaction":{"profile":"public_safe"}}' \
  | python3 -m json.tool
```

**B. No-token** — API routes intentionally remain open:

```bash
curl -s -X POST http://localhost:8377/api/reports \
  -H "Content-Type: application/json" \
  -d '{"scope":"full","format":"json","redaction":{"profile":"public_safe"}}' \
  | python3 -m json.tool
```

Download the stored report (replace `<report-id>`):

**A. Token-enabled:**

```bash
curl -s \
  -H "Authorization: Bearer $ZIGBEELENS_TEST_API_TOKEN" \
  "http://localhost:8377/api/reports/<report-id>/download" \
  -o report.json
grep -iE 'password|network_key|secret' report.json || echo "No obvious secret keys in report"
```

**B. No-token trusted-open:**

```bash
curl -s \
  "http://localhost:8377/api/reports/<report-id>/download" \
  -o report.json
grep -iE 'password|network_key|secret' report.json || echo "No obvious secret keys in report"
```

Open the dashboard: **http://localhost:8377**

---

## 3. Container smoke checklist

- [ ] Image pulls from GHCR (`:edge`)
- [ ] Container starts without crash loop
- [ ] `/api/health` returns `"status": "ok"` (or equivalent healthy payload)
- [ ] `/api/capabilities` returns `decision_contract_version == 1`
- [ ] Capabilities include `shared_decisions` and `companion_decision_summary`
- [ ] Required Dashboard surfaces are advertised; `dashboard_recent_changes` is absent
- [ ] `/api/dashboard` includes `investigation_priorities` and `data_coverage_warnings` lists
- [ ] UI loads at `/`
- [ ] Static assets load (no blank page / 404 on JS/CSS)
- [ ] SQLite database created under mounted `/data` (`zigbeelens.sqlite`)
- [ ] MQTT collector connects (`collector.connected: true` in `/api/health`)
- [ ] Both configured networks appear (`home`, `home2`)
- [ ] Devices appear for each network
- [ ] Overview shows ranked investigation priorities when evidence qualifies (empty is OK)
- [ ] Devices list shows Device Story decision badges
- [ ] Device Detail uses Device Story
- [ ] Incidents separate recorded event from current device decisions
- [ ] Reports Version 2 uses shared decisions (`device_stories` present)
- [ ] Incidents appear only if real conditions warrant (empty is OK)
- [ ] Settings page shows collector status and both networks
- [ ] Settings storage section shows retention policy (telemetry / resolved incidents / reports) and no Purge/Vacuum/Backup controls
- [ ] Reports page generates **JSON**
- [ ] Reports page generates **YAML**
- [ ] Reports page generates **Markdown**
- [ ] `public_safe` report redacts names/IEEE/host/IP as expected (API example below)
- [ ] No MQTT password in downloaded report
- [ ] No `network_key` in downloaded report
- [ ] Container logs do not show MQTT password (`docker logs zigbeelens`)

### Track 6 storage upgrade / backup / dry-run checklist

Run against the release-test data volume (or a copy). Prefer Core stopped for `--apply`; online backup is safe while Core runs.

- [ ] Upgrade starts Core: migration version includes **012**, then integrity gates, then first maintenance cycle (check logs / Settings)
- [ ] `GET /api/storage/status` returns policy defaults (`telemetry_retention_days: 7`, resolved incidents `90`, `report_retention_days: null`)
- [ ] Before first successful maintenance persistence, deletion totals may be `null`; after success, timestamps and counts are present
- [ ] Integrity facts expose `quick_check` and `foreign_key_check` (`status` / `checked_at` / `violation_count`)
- [ ] Online backup: `zigbeelens storage backup --config … --output …` then `zigbeelens storage check --database …` (symlink-safe publish; no WAL-only copy)
- [ ] `zigbeelens storage check` is non-mutating (read-only; no migrate / no status write)
- [ ] `zigbeelens storage maintenance --dry-run` previews eligibility without mutations or status updates
- [ ] `zigbeelens storage maintenance --apply` does **not** run migrations (schema mismatch refused); Core startup owns migrations
- [ ] Reports remain until manually deleted by default; resolved incidents age at 90 days unless retention is null
- [ ] No automatic `VACUUM`; Settings still has no purge/backup UI

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
- [ ] Trusted-open Core + blank HACS token succeeds
- [ ] Protected Core + missing/wrong token → invalid auth / reauth (not a misleading unreachable loop)
- [ ] Protected Core + correct token → entities/panel/repairs work
- [ ] Rotate Core token → HA linked reauth → enter new token → updates recover
- [ ] Diagnostics show `api_token_configured` and contain no token value
- [ ] Open Full Dashboard still uses standalone login (no HACS token in URL)
- [ ] Existing summary entities still appear (overall health, active incident, counts)
- [ ] Per-network sensors appear (`Home`, `Home 2`)
- [ ] No new decision entities appear for priorities / Device Stories
- [ ] Existing entity unique IDs remain stable
- [ ] No mutation controls/services appear
- [ ] Sidebar **ZigbeeLens** entry appears
- [ ] Same-scheme HA/Core stays on native summary until Try Embedded View
- [ ] Mixed-content (HTTPS HA + HTTP Core) uses the native companion summary / blocked view
- [ ] Back to Summary returns from embedded or blocked view to native summary
- [ ] Diagnostics show `decision_contract_version`, `shared_decisions_available`, `core_version_compatible`
- [ ] Contract v1 activates decision mode when Dashboard surfaces are valid lists
- [ ] Panel priority label/title/summary match Core Dashboard exactly
- [ ] Top-three priority cap and “+N more …” behaviour
- [ ] Coverage warning count appears as a factual count
- [ ] Decision mode has no Health authority badge and no Current finding card
- [ ] Valid empty priorities show: `No current investigation priorities from stored evidence.`
- [ ] Unsupported/malformed contract uses factual fallback mode
- [ ] Disconnected Core shows compatibility Unknown, not Compatible
- [ ] Open Full Dashboard opens Core in a new tab
- [ ] Try Embedded View shows a friendly explanation if Home Assistant is HTTPS and Core is HTTP
- [ ] Settings → Devices & services → ZigbeeLens → Reconfigure can change Core URL / token without delete/re-add
- [ ] Configure (options) adjusts panel/polling only
- [ ] If using an HTTPS Core URL, Try Embedded View displays the full dashboard inside Home Assistant
- [ ] *(Optional advanced)* Caddy HTTPS stack from [hacs-embedded-view.md](hacs-embedded-view.md): Core URL updated, cert trusted, embedded view works
- [ ] Core connected state appears
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
5. Open the ZigbeeLens sidebar — native summary is the default; use **Try Embedded View** to enter iframe mode.
6. **Open Full Dashboard** opens the HTTPS URL in a new tab.
7. **Try Embedded View** — full dashboard renders inside Home Assistant when embedding is allowed.
8. **Back to Summary** returns to the native companion panel (usable even if CSP blocks the iframe).

### Companion panel notes

- The **Core dashboard is canonical** — HACS does not build a second dashboard or drill-down pages.
- The companion panel is a **status/launcher surface**: it renders a redacted summary supplied by the integration over the HA websocket, so the browser never fetches Core directly for the summary.
- Native summary is the default; same-scheme setups can opt into embedded Core via Try Embedded View; mixed content cannot embed.
- **Open Full Dashboard** opens Core in a new tab and remains the reliable investigation route.
- **Try Embedded View** is optional and only works when browser security allows embedding; **Back to Summary** exits iframe mode.
- Decision mode (contract v1) applies only on the native summary path.
- Optional HTTPS reverse proxy for embedded view: [hacs-embedded-view.md](hacs-embedded-view.md)

---

## 4b. Add-on validation path

- [ ] `./scripts/validate-addon.sh`
- [ ] `./scripts/prepare-addon.sh`
- [ ] Optional: `./scripts/build-addon.sh` when Docker is available
- [ ] Ingress loads current Core UI
- [ ] `/api/capabilities` exposes contract v1
- [ ] No separate add-on decision wording layer
- [ ] Topology startup-scan policy matches documented safety limits

## 5. Safety checks (pre-release)

- [ ] MQTT Discovery **disabled** in config (`features.mqtt_discovery: false`)
- [ ] Topology enabled with startup scan only (`topology.startup_scan: true`, `refresh_interval_seconds: 0`)
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
