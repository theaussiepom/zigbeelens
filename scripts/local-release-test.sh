#!/usr/bin/env bash
# Local pre-release smoke test helper — no secrets, uses GHCR :edge image.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${ZIGBEELENS_IMAGE:-ghcr.io/theaussiepom/zigbeelens:edge}"
CONFIG_DIR="${ROOT}/local/zigbeelens-test/config"
DATA_DIR="${ROOT}/local/zigbeelens-test/data"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"
TEMPLATE="${CONFIG_DIR}/config.yaml.example"

mkdir -p "${CONFIG_DIR}" "${DATA_DIR}"

if [[ ! -f "${CONFIG_FILE}" ]]; then
  if [[ -f "${TEMPLATE}" ]]; then
    cp "${TEMPLATE}" "${CONFIG_FILE}"
    echo "Created ${CONFIG_FILE} from template."
    echo "Edit it now — replace <your-mqtt-host>, <mqtt-user>, <mqtt-password>"
    exit 1
  else
    echo "ERROR: Missing ${CONFIG_FILE} and ${TEMPLATE}" >&2
    exit 1
  fi
fi

if grep -q '<your-mqtt-host>' "${CONFIG_FILE}"; then
  echo "ERROR: ${CONFIG_FILE} still contains placeholder <your-mqtt-host>" >&2
  echo "Edit the file with your real MQTT broker details before running." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found" >&2
  exit 1
fi

echo "Pulling ${IMAGE}..."
docker pull "${IMAGE}"

echo "Starting ZigbeeLens (Ctrl+C to stop)..."
echo "Dashboard: http://localhost:8377"
echo "Verify:    curl http://localhost:8377/healthz"

docker run --rm \
  --name zigbeelens \
  -p 8377:8377 \
  -v "${CONFIG_DIR}:/config:ro" \
  -v "${DATA_DIR}:/data" \
  "${IMAGE}"
