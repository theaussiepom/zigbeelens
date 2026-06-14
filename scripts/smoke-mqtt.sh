#!/usr/bin/env bash
# Smoke test: optional MQTT broker check — skips if mosquitto unavailable.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BROKER="${SMOKE_MQTT:-mqtt://127.0.0.1:1883}"
BASE_TOPIC="${SMOKE_BASE_TOPIC:-zigbee2mqtt}"

if ! command -v mosquitto_pub >/dev/null 2>&1; then
  echo "SKIP: mosquitto_pub not available"
  exit 0
fi

if ! mosquitto_pub -h 127.0.0.1 -t "test/zigbeelens/smoke" -m "ping" 2>/dev/null; then
  echo "SKIP: MQTT broker not reachable at ${BROKER}"
  exit 0
fi

echo "=== smoke-mqtt: publishing sample bridge state ==="
mosquitto_pub -h 127.0.0.1 -t "${BASE_TOPIC}/bridge/state" -m '{"state":"online"}' || true
mosquitto_pub -h 127.0.0.1 -t "${BASE_TOPIC}/bridge/devices" -m '[]' || true

echo "OK: smoke-mqtt published sample payloads (manual Core verification required for full E2E)"
