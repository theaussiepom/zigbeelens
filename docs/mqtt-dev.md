# Testing against a real MQTT broker

With live mode and the collector enabled:

```bash
export ZIGBEELENS_CONFIG=config/config.live.example.yaml
source apps/core/.venv/bin/activate
PYTHONPATH=apps/core/src python -m zigbeelens
```

Bind address and port come from the effective AppConfig (`server.host` / `server.port`). The source default is loopback (`127.0.0.1:8377`).

Publish sample Zigbee2MQTT messages from a separate test client:

```bash
mosquitto_pub -t 'zigbee2mqtt/bridge/state' -m 'online'
mosquitto_pub -t 'zigbee2mqtt/bridge/devices' -m '[{"ieee_address":"0x00124b0024abcd01","friendly_name":"Laundry Plug","type":"Router","power_source":"Mains (single phase)","model_id":"TS011F","manufacturer":"_TZ3000_test","interview_completed":true}]'
mosquitto_pub -t 'zigbee2mqtt/Laundry Plug' -m '{"linkquality":76,"state":"ON","last_seen":"2026-06-14T10:00:00+10:00"}'
mosquitto_pub -t 'zigbee2mqtt/Laundry Plug/availability' -m '{"state":"online"}'
```

Inspect live state:

- `GET /api/v1/health` — includes collector connection status
- `GET /api/v1/dashboard` — live networks/devices once messages arrive
- `GET /api/v1/networks`
- `GET /api/v1/devices`
- `GET /api/v1/timeline`

The production collector subscribes to these patterns per configured base
topic:

```text
{base_topic}/bridge/state
{base_topic}/bridge/info
{base_topic}/bridge/devices
{base_topic}/bridge/event
{base_topic}/bridge/logging
{base_topic}/bridge/health
{base_topic}/+/availability
{base_topic}/+
```

When topology is enabled it also subscribes to
`{base_topic}/bridge/response/networkmap`. The collector client is
subscribe-only and never publishes device `/set` commands.

Topology is a separate diagnostic publisher. With the source defaults it issues
one startup request per network after collector/bridge readiness:

```text
{base_topic}/bridge/request/networkmap
```

If the development broker user is strictly subscribe-only, disable
`topology.startup_scan` (or topology entirely). Otherwise grant publish only to
that exact request topic. MQTT Discovery is another optional publisher and
needs separate ACLs for its configured discovery/state prefixes.

See [safety-audit.md](safety-audit.md) for the complete subscription and publish
boundary.
