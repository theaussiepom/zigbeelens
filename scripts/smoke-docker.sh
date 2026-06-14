#!/usr/bin/env bash
# Smoke test: build Docker image, run container, verify health endpoint.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${SMOKE_DOCKER_PORT:-8378}"
IMAGE="${SMOKE_IMAGE:-zigbeelens-smoke:local}"
CONTAINER="zigbeelens-smoke-$$"
CONFIG_DIR="${ROOT}/.smoke-config"
DATA_DIR="${ROOT}/.smoke-data"

cleanup() {
  docker rm -f "${CONTAINER}" 2>/dev/null || true
}
trap cleanup EXIT

if ! command -v docker >/dev/null 2>&1; then
  echo "SKIP: docker not available"
  exit 0
fi

mkdir -p "${CONFIG_DIR}" "${DATA_DIR}"
cp "${ROOT}/deploy/docker/config.example.yaml" "${CONFIG_DIR}/config.yaml"

echo "=== smoke-docker: building ${IMAGE} ==="
docker build -f "${ROOT}/deploy/docker/Dockerfile" -t "${IMAGE}" "${ROOT}"

echo "=== smoke-docker: running container ==="
docker run -d --name "${CONTAINER}" \
  -p "${PORT}:8377" \
  -v "${CONFIG_DIR}:/config:ro" \
  -v "${DATA_DIR}:/data" \
  "${IMAGE}"

BASE="http://127.0.0.1:${PORT}"
for i in $(seq 1 60); do
  if curl -sf "${BASE}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -sf "${BASE}/api/health" | grep -q '"status"' || { echo "FAIL: /api/health"; exit 1; }
curl -sf "${BASE}/" -o /dev/null || { echo "FAIL: /"; exit 1; }

echo "OK: smoke-docker passed"
