## Testing against a real MQTT broker

With live mode and the collector enabled:

```bash
export ZIGBEELENS_CONFIG=config/config.live.example.yaml
source apps/core/.venv/bin/activate
PYTHONPATH=apps/core/src uvicorn zigbeelens.main:app --host 0.0.0.0 --port 8377
```

Publish sample Zigbee2MQTT messages:

```bash
mosquitto_pub -t 'zigbee2mqtt/bridge/state' -m 'online'
mosquitto_pub -t 'zigbee2mqtt/bridge/devices' -m '[{"ieee_address":"0x00124b0024abcd01","friendly_name":"Laundry Plug","type":"Router","power_source":"Mains (single phase)","model_id":"TS011F","manufacturer":"_TZ3000_test","interview_completed":true}]'
mosquitto_pub -t 'zigbee2mqtt/Laundry Plug' -m '{"linkquality":76,"state":"ON","last_seen":"2026-06-14T10:00:00+10:00"}'
mosquitto_pub -t 'zigbee2mqtt/Laundry Plug/availability' -m '{"state":"online"}'
```

Inspect live state:

- `GET /api/health` — includes collector connection status
- `GET /api/dashboard` — live networks/devices once messages arrive
- `GET /api/networks`
- `GET /api/devices`
- `GET /api/timeline`

ZigbeeLens is read-only: it never publishes to `bridge/request/*` or `{friendly_name}/set`.
