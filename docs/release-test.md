# Local test guide — deployed GHCR image + HACS integration

Replace `theaussiepom` with your GitHub owner if different.

## 1. Pull and run published container

After the main repo `main` branch publishes to GHCR:

```bash
mkdir -p zigbeelens-test/config zigbeelens-test/data

cat > zigbeelens-test/config/config.yaml <<'EOF'
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

storage:
  path: /data/zigbeelens.sqlite
  retention_days: 30

features:
  mqtt_collector: true
  mqtt_discovery: false
  bridge_logs: true
  device_payload_history: true
  manual_network_map: false
  automatic_network_map: false
EOF

docker run --rm \
  --name zigbeelens \
  -p 8377:8377 \
  -v "$PWD/zigbeelens-test/config:/config:ro" \
  -v "$PWD/zigbeelens-test/data:/data" \
  ghcr.io/theaussiepom/zigbeelens:edge
```

Verify:

```bash
curl http://localhost:8377/api/health
curl http://localhost:8377/api/dashboard
```

Open http://localhost:8377

## 2. Install HACS integration

In Home Assistant:

1. **HACS → Integrations → Custom repositories**
2. Add: `https://github.com/theaussiepom/zigbeelens-hacs`
3. Category: **Integration**
4. Install **ZigbeeLens** and restart Home Assistant
5. **Settings → Devices & services → Add Integration → ZigbeeLens**
6. Core URL: `http://<docker-host-ip>:8377` (must be reachable from HA, not only your browser)
7. Enable sidebar panel if desired

## 3. Confirm entities and panel

Expected summary entities include:

- `binary_sensor.zigbeelens_active_incident`
- `sensor.zigbeelens_overall_health`
- `sensor.zigbeelens_unavailable_devices`
- `sensor.zigbeelens_router_risks`

Sidebar panel should open the Core dashboard. If iframe embedding is blocked, use the Core URL link directly.

## 4. Safety checks

- Reports generate with redaction
- `/api/health` shows collector subscribe-only status
- MQTT Discovery and topology disabled by default

## 5. Add-on repo (later)

Add-on store: `https://github.com/theaussiepom/zigbeelens-addons`

Uses GHCR image `ghcr.io/theaussiepom/zigbeelens` — add-on version tag must exist on GHCR (e.g. `0.1.0`) or use Docker `:edge` for pre-release testing.
