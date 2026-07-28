#!/usr/bin/env bash
# Hermetic standalone-image smoke through the canonical clean-tree build owner.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
IMAGE="${SMOKE_IMAGE:-zigbeelens-smoke:local}"
EXPECTED_SOURCE="https://github.com/theaussiepom/zigbeelens"
REQUIRE_DOCKER="${ZIGBEELENS_REQUIRE_DOCKER:-1}"
READINESS_TIMEOUT_SECONDS="${SMOKE_DOCKER_READINESS_TIMEOUT_SECONDS:-60}"

STATE_DIR=""
STATE_DIR_VALIDATED=0
RESOLVED_STATE_DIR=""
STATE_TOKEN=""
CONTAINER_NAME=""
CONTAINER_ID=""
CONTAINER_ID_VALIDATED=0
CONTAINER_RUN_ATTEMPTED=0
LOG_PRINTED=0
SMOKE_SUCCEEDED=0
DOCKER_COMMAND=""
PYTHON_COMMAND=""
CURL_COMMAND=""
SENSITIVE_LOG_PATTERN='Authorization:[[:space:]]*(Bearer|Basic)[[:space:]]+|("?password"?|"?api[_ -]?(token|key)"?|"?token"?|"?credential(s)?"?|"?session[_ -]?secret"?)[[:space:]]*[:=][[:space:]]*"?[^[:space:]",}]+'
FORBIDDEN_ACTIVITY_LOG_PATTERN='MQTT.*(connect|subscrib|publish|failed to start)|Discovery (publication|publish)|[Pp]ublishing .*Discovery|topology (request|capture)|network[- ]map request|Traceback \(most recent call last\)|[Uu]nhandled exception|ConnectionRefusedError|socket\.gaierror|getaddrinfo'

capture_container_log() {
  if [[ -z "${CONTAINER_ID}" || -z "${STATE_DIR}" ]]; then
    return 1
  fi
  "${DOCKER_COMMAND}" logs "${CONTAINER_ID}" \
    >"${STATE_DIR}/container.log" 2>&1
}

print_safe_container_log() {
  if (( LOG_PRINTED )) || [[ -z "${STATE_DIR}" ]]; then
    return 0
  fi
  capture_container_log || true
  if [[ -s "${STATE_DIR}/container.log" ]]; then
    echo "=== smoke-docker: safe container log ===" >&2
    if LC_ALL=C grep -Eiq \
      "${SENSITIVE_LOG_PATTERN}" "${STATE_DIR}/container.log"
    then
      LC_ALL=C grep -Eiv \
        "${SENSITIVE_LOG_PATTERN}" "${STATE_DIR}/container.log" |
        sed -n '1,240p' >&2 || true
      echo "[sensitive-looking container log lines withheld]" >&2
    else
      sed -n '1,240p' "${STATE_DIR}/container.log" >&2
    fi
  fi
  LOG_PRINTED=1
}

cleanup() {
  local status=$?
  local cleanup_candidate=""
  local cleanup_owner=""
  local cleanup_failed=0
  trap - EXIT HUP INT TERM
  if (( ! CONTAINER_ID_VALIDATED )) &&
    [[ -n "${STATE_DIR}" && -s "${STATE_DIR}/container.cid" ]]
  then
    IFS= read -r cleanup_candidate <"${STATE_DIR}/container.cid" || true
    if [[ ${#cleanup_candidate} -eq 64 &&
      "${cleanup_candidate}" != *[!0-9a-f]* ]]
    then
      CONTAINER_ID="${cleanup_candidate}"
      CONTAINER_ID_VALIDATED=1
    fi
  fi
  if (( ! CONTAINER_ID_VALIDATED && CONTAINER_RUN_ATTEMPTED )) &&
    [[ -n "${DOCKER_COMMAND}" && -n "${CONTAINER_NAME}" ]]
  then
    cleanup_candidate="$(
      "${DOCKER_COMMAND}" inspect "${CONTAINER_NAME}" \
        --format '{{.Id}}' 2>/dev/null || true
    )"
    cleanup_owner="$(
      "${DOCKER_COMMAND}" inspect "${CONTAINER_NAME}" \
        --format '{{ index .Config.Labels "com.zigbeelens.smoke.owner" }}' \
        2>/dev/null || true
    )"
    if [[ ${#cleanup_candidate} -eq 64 &&
      "${cleanup_candidate}" != *[!0-9a-f]* &&
      "${cleanup_owner}" == "${STATE_TOKEN}" ]]
    then
      CONTAINER_ID="${cleanup_candidate}"
      CONTAINER_ID_VALIDATED=1
    elif [[ -n "${cleanup_candidate}" ]]; then
      echo \
        "ERROR: refused to remove an unverified Docker container named ${CONTAINER_NAME}" \
        >&2
      cleanup_failed=1
    fi
  fi
  if (( CONTAINER_ID_VALIDATED )) && [[ -n "${DOCKER_COMMAND}" ]]; then
    if (( status != 0 )); then
      print_safe_container_log
    fi
    if ! "${DOCKER_COMMAND}" rm -f "${CONTAINER_ID}" >/dev/null 2>&1; then
      echo "ERROR: failed to remove Docker smoke container ${CONTAINER_ID}" >&2
      cleanup_failed=1
    elif "${DOCKER_COMMAND}" inspect "${CONTAINER_ID}" >/dev/null 2>&1; then
      echo "ERROR: Docker smoke container still exists after cleanup" >&2
      cleanup_failed=1
    fi
  fi
  if (( STATE_DIR_VALIDATED )) && [[ -n "${STATE_DIR}" && -d "${STATE_DIR}" ]]; then
    if ! rm -rf -- "${STATE_DIR}" || [[ -e "${STATE_DIR}" ]]; then
      echo "ERROR: failed to remove Docker smoke state ${STATE_DIR}" >&2
      cleanup_failed=1
    fi
  fi
  if (( cleanup_failed )) && (( status == 0 )); then
    status=1
  fi
  if (( status == 0 && SMOKE_SUCCEEDED )); then
    echo "OK: smoke-docker passed"
    echo "image_id=${IMAGE_ID}"
    echo \
      "version=${IMAGE_VERSION} revision=${IMAGE_REVISION} source=${IMAGE_SOURCE}"
    echo "runtime=healthy schema=15 mqtt_attempts=0 topology_attempts=0"
  fi
  exit "${status}"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

case "${REQUIRE_DOCKER}" in
  0 | 1) ;;
  *) fail "ZIGBEELENS_REQUIRE_DOCKER must be 0 or 1" ;;
esac

if [[ ! "${READINESS_TIMEOUT_SECONDS}" =~ ^[0-9]{1,3}$ ]] ||
  (( 10#${READINESS_TIMEOUT_SECONDS} < 1 ||
    10#${READINESS_TIMEOUT_SECONDS} > 300 ))
then
  fail "SMOKE_DOCKER_READINESS_TIMEOUT_SECONDS must be an integer from 1 to 300"
fi
READINESS_TIMEOUT_SECONDS=$((10#${READINESS_TIMEOUT_SECONDS}))

if ! DOCKER_COMMAND="$(command -v docker 2>/dev/null)" ||
  [[ -z "${DOCKER_COMMAND}" ]]
then
  if [[ "${REQUIRE_DOCKER}" == "0" ]]; then
    echo "SKIP: docker command not available (non-release opt-out)"
    exit 0
  fi
  fail "docker is required for the standalone image smoke"
fi
if ! "${DOCKER_COMMAND}" info >/dev/null 2>&1; then
  if [[ "${REQUIRE_DOCKER}" == "0" ]]; then
    echo "SKIP: docker daemon not available (non-release opt-out)"
    exit 0
  fi
  fail "docker daemon is required for the standalone image smoke"
fi
if ! CURL_COMMAND="$(command -v curl 2>/dev/null)" ||
  [[ -z "${CURL_COMMAND}" ]]
then
  fail "curl is required for the standalone image smoke"
fi
if ! PYTHON_COMMAND="$(command -v python3 2>/dev/null)" ||
  [[ -z "${PYTHON_COMMAND}" ]]
then
  fail "python3 is required for the standalone image smoke"
fi

EXPLICIT_PORT=0
PORT=""
if [[ "${SMOKE_DOCKER_PORT+x}" == "x" ]]; then
  if [[ -z "${SMOKE_DOCKER_PORT}" ]]; then
    fail "SMOKE_DOCKER_PORT must be an integer from 1 to 65535"
  fi
  if [[ ! "${SMOKE_DOCKER_PORT}" =~ ^[0-9]{1,5}$ ]]; then
    fail "SMOKE_DOCKER_PORT must be an integer from 1 to 65535"
  fi
  PORT=$((10#${SMOKE_DOCKER_PORT}))
  if (( PORT < 1 || PORT > 65535 )); then
    fail "SMOKE_DOCKER_PORT must be an integer from 1 to 65535"
  fi
  if ! "${PYTHON_COMMAND}" - "${PORT}" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.bind(("127.0.0.1", port))
PY
  then
    fail "SMOKE_DOCKER_PORT is unavailable on 127.0.0.1:${PORT}"
  fi
  EXPLICIT_PORT=1
fi

TMP_BASE="${TMPDIR:-/tmp}"
if ! TMP_BASE="$(cd "${TMP_BASE}" 2>/dev/null && pwd -P)"; then
  fail "temporary directory root is unavailable: ${TMPDIR:-/tmp}"
fi
if ! STATE_DIR="$(mktemp -d "${TMP_BASE}/zigbeelens-docker-smoke.XXXXXX")"; then
  fail "unable to create external Docker smoke state"
fi
case "${STATE_DIR}" in
  "${TMP_BASE}"/zigbeelens-docker-smoke.*) STATE_DIR_VALIDATED=1 ;;
  *) fail "Docker smoke state did not use the owned temporary prefix" ;;
esac
if ! RESOLVED_STATE_DIR="$(cd "${STATE_DIR}" && pwd -P)"; then
  fail "unable to resolve the external Docker smoke state"
fi
STATE_DIR="${RESOLVED_STATE_DIR}"
case "${STATE_DIR}/" in
  "${ROOT}/"*) fail "Docker smoke state must be outside the Git checkout" ;;
esac
STATE_TOKEN="${STATE_DIR##*.}"
if [[ -z "${STATE_TOKEN}" || "${STATE_TOKEN}" == *[!A-Za-z0-9]* ]]; then
  fail "Docker smoke state has an invalid ownership token"
fi
CONTAINER_NAME="zigbeelens-smoke-${STATE_TOKEN}"

CONFIG_DIR="${STATE_DIR}/config"
DATA_DIR="${STATE_DIR}/data"
CONFIG_PATH="${CONFIG_DIR}/config.yaml"
CID_PATH="${STATE_DIR}/container.cid"
RUN_OUTPUT_PATH="${STATE_DIR}/docker-run.out"
RUN_ERROR_PATH="${STATE_DIR}/docker-run.err"
HEALTHZ_PATH="${STATE_DIR}/healthz.json"
VERSION_PATH="${STATE_DIR}/version.json"
VERSION_V1_PATH="${STATE_DIR}/version-v1.json"
API_HEALTH_PATH="${STATE_DIR}/api-health.json"
STORAGE_STATUS_PATH="${STATE_DIR}/storage-status.json"
CONFIG_STATUS_PATH="${STATE_DIR}/config-status.json"
UI_ROOT_PATH="${STATE_DIR}/ui-root.html"

mkdir -p "${CONFIG_DIR}" "${DATA_DIR}"
chmod 0755 "${CONFIG_DIR}"
chmod 0777 "${DATA_DIR}"
cat >"${CONFIG_PATH}" <<'YAML'
server:
  host: 0.0.0.0
  port: 8377

mode:
  mock: true
  default_scenario: four_devices_same_room_unavailable

security:
  mode: local

mqtt:
  server: ""
  username: ""
  password: ""
  client_id: zigbeelens-docker-smoke
  tls:
    enabled: false
    reject_unauthorized: true

networks:
  - id: docker-smoke
    name: Docker smoke
    base_topic: zigbeelens-docker-smoke-unused

storage:
  path: /data/zigbeelens.sqlite
  retention_days: 1
  resolved_incident_retention_days: 1
  report_retention_days: null
  maintenance_interval_hours: 24

features:
  mqtt_collector: false
  mqtt_discovery: false
  bridge_logs: false
  device_payload_history: false
  manual_network_map: false
  automatic_network_map: false

mqtt_discovery:
  enabled: false

topology:
  enabled: false
  startup_scan: false
  refresh_interval_seconds: 0
  manual_capture_enabled: false
  automatic_capture_enabled: false
  capture_on_incident: false
YAML
chmod 0444 "${CONFIG_PATH}"

EXPECTED_VERSION="$(
  sed -nE 's/.*"version": "([^"]+)".*/\1/p' "${ROOT}/package.json" | head -1
)"
if [[ "${EXPECTED_VERSION}" != "0.1.14" ]]; then
  fail "standalone Docker smoke requires package version 0.1.14"
fi
if ! EXPECTED_REVISION="$(
  git -C "${ROOT}" rev-parse --verify 'HEAD^{commit}' 2>/dev/null
)"; then
  fail "unable to resolve the exact Docker smoke source revision"
fi
if [[ ${#EXPECTED_REVISION} -ne 40 ||
  "${EXPECTED_REVISION}" == *[!0-9a-f]* ]]
then
  fail "Docker smoke source revision must be a full lowercase Git SHA"
fi

echo "=== smoke-docker: state ${STATE_DIR} ==="
echo "=== smoke-docker: building ${IMAGE} from ${EXPECTED_REVISION} ==="
ZIGBEELENS_IMAGE="${IMAGE}" "${ROOT}/scripts/build-docker.sh"

IMAGE_ID="$(
  "${DOCKER_COMMAND}" image inspect "${IMAGE}" --format '{{.Id}}'
)"
IMAGE_VERSION="$(
  "${DOCKER_COMMAND}" image inspect "${IMAGE}" \
    --format '{{ index .Config.Labels "org.opencontainers.image.version" }}'
)"
IMAGE_REVISION="$(
  "${DOCKER_COMMAND}" image inspect "${IMAGE}" \
    --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'
)"
IMAGE_SOURCE="$(
  "${DOCKER_COMMAND}" image inspect "${IMAGE}" \
    --format '{{ index .Config.Labels "org.opencontainers.image.source" }}'
)"
IMAGE_USER="$(
  "${DOCKER_COMMAND}" image inspect "${IMAGE}" --format '{{.Config.User}}'
)"
if [[ ! "${IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  fail "built image has no canonical image ID"
fi
[[ "${IMAGE_VERSION}" == "${EXPECTED_VERSION}" ]] ||
  fail "built image OCI version mismatch"
[[ "${IMAGE_REVISION}" == "${EXPECTED_REVISION}" ]] ||
  fail "built image OCI revision mismatch"
[[ "${IMAGE_SOURCE}" == "${EXPECTED_SOURCE}" ]] ||
  fail "built image OCI source mismatch"
[[ "${IMAGE_USER}" == "zigbeelens" ]] ||
  fail "built image must run as the zigbeelens user"

if (( EXPLICIT_PORT )); then
  PORT_BIND="127.0.0.1:${PORT}:8377"
else
  PORT_BIND="127.0.0.1::8377"
fi

echo "=== smoke-docker: running isolated container ==="
if "${DOCKER_COMMAND}" inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
  fail "unexpected Docker container name collision: ${CONTAINER_NAME}"
fi
CONTAINER_RUN_ATTEMPTED=1
if ! "${DOCKER_COMMAND}" run -d --pull never \
  --name "${CONTAINER_NAME}" \
  --label "com.zigbeelens.smoke.owner=${STATE_TOKEN}" \
  --cidfile "${CID_PATH}" \
  --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,mode=1777 \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  -p "${PORT_BIND}" \
  --mount "type=bind,src=${CONFIG_DIR},dst=/config,readonly" \
  --mount "type=bind,src=${DATA_DIR},dst=/data" \
  "${IMAGE}" >"${RUN_OUTPUT_PATH}" 2>"${RUN_ERROR_PATH}"
then
  if [[ -s "${CID_PATH}" ]]; then
    IFS= read -r CONTAINER_ID <"${CID_PATH}" || true
    if [[ ${#CONTAINER_ID} -eq 64 &&
      "${CONTAINER_ID}" != *[!0-9a-f]* ]]
    then
      CONTAINER_ID_VALIDATED=1
    fi
  fi
  if [[ -s "${RUN_ERROR_PATH}" ]]; then
    sed -n '1,120p' "${RUN_ERROR_PATH}" >&2
  fi
  fail "Docker smoke container failed to start"
fi
CONTAINER_ID=""
IFS= read -r CONTAINER_ID <"${CID_PATH}" || true
[[ -n "${CONTAINER_ID}" ]] ||
  fail "Docker did not record the smoke container ID"
if [[ ${#CONTAINER_ID} -ne 64 || "${CONTAINER_ID}" == *[!0-9a-f]* ]]; then
  fail "Docker recorded an invalid smoke container ID"
fi
CONTAINER_ID_VALIDATED=1

CONTAINER_IMAGE_ID="$(
  "${DOCKER_COMMAND}" inspect "${CONTAINER_ID}" --format '{{.Image}}'
)"
[[ "${CONTAINER_IMAGE_ID}" == "${IMAGE_ID}" ]] ||
  fail "running container image ID does not match the image just built"

PORT_OUTPUT="$(
  "${DOCKER_COMMAND}" port "${CONTAINER_ID}" 8377/tcp
)"
if [[ "${PORT_OUTPUT}" =~ ^127\.0\.0\.1:([0-9]{1,5})$ ]]; then
  PUBLISHED_PORT=$((10#${BASH_REMATCH[1]}))
else
  fail "Docker did not publish the smoke endpoint on loopback only"
fi
if (( PUBLISHED_PORT < 1 || PUBLISHED_PORT > 65535 )); then
  fail "Docker returned an invalid published smoke port"
fi
if (( EXPLICIT_PORT )) && (( PUBLISHED_PORT != PORT )); then
  fail "Docker published a different port than SMOKE_DOCKER_PORT"
fi
PORT="${PUBLISHED_PORT}"
BASE="http://127.0.0.1:${PORT}"

curl_smoke() {
  "${CURL_COMMAND}" \
    --fail \
    --silent \
    --show-error \
    --noproxy '*' \
    --connect-timeout 2 \
    --max-time 5 \
    "$@"
}

READY=0
START_SECONDS=${SECONDS}
while (( SECONDS - START_SECONDS < READINESS_TIMEOUT_SECONDS )); do
  RUNNING="$(
    "${DOCKER_COMMAND}" inspect "${CONTAINER_ID}" \
      --format '{{.State.Running}}' 2>/dev/null || true
  )"
  if [[ "${RUNNING}" != "true" ]]; then
    fail "Docker smoke container exited before readiness"
  fi
  if curl_smoke "${BASE}/healthz" >"${HEALTHZ_PATH}" 2>/dev/null; then
    READY=1
    break
  fi
  sleep 0.25
done
if (( ! READY )); then
  fail "Docker smoke readiness timed out after ${READINESS_TIMEOUT_SECONDS}s"
fi

fetch_endpoint() {
  local label="$1"
  local path="$2"
  local output_path="$3"
  if ! curl_smoke "${BASE}${path}" >"${output_path}"; then
    fail "${label} endpoint failed: ${path}"
  fi
}

fetch_endpoint "health" "/healthz" "${HEALTHZ_PATH}"
fetch_endpoint "version" "/api/version" "${VERSION_PATH}"
fetch_endpoint "v1 version" "/api/v1/version" "${VERSION_V1_PATH}"
fetch_endpoint "API health" "/api/health" "${API_HEALTH_PATH}"
fetch_endpoint "storage status" "/api/storage/status" "${STORAGE_STATUS_PATH}"
fetch_endpoint "config status" "/api/config/status" "${CONFIG_STATUS_PATH}"
fetch_endpoint "bundled UI" "/" "${UI_ROOT_PATH}"

"${PYTHON_COMMAND}" -I - \
  "${EXPECTED_VERSION}" \
  "${HEALTHZ_PATH}" \
  "${VERSION_PATH}" \
  "${VERSION_V1_PATH}" \
  "${API_HEALTH_PATH}" \
  "${STORAGE_STATUS_PATH}" \
  "${CONFIG_STATUS_PATH}" \
  "${UI_ROOT_PATH}" <<'PY'
import json
import sys
from pathlib import Path

(
    expected_version,
    healthz_path,
    version_path,
    version_v1_path,
    api_health_path,
    storage_status_path,
    config_status_path,
    ui_root_path,
) = sys.argv[1:]


def read_json(path: str) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} did not contain a JSON object")
    return payload


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Docker smoke runtime contract failed: {message}")


healthz = read_json(healthz_path)
version = read_json(version_path)
version_v1 = read_json(version_v1_path)
api_health = read_json(api_health_path)
storage = read_json(storage_status_path)
config = read_json(config_status_path)

require(healthz == {"status": "ok"}, "/healthz status")
require(
    version == {"version": expected_version, "name": "zigbeelens-core"},
    "/api/version identity",
)
require(version_v1 == version, "/api/v1/version parity")
require(api_health["status"] == "ok", "/api/health status")
require(api_health["version"] == expected_version, "/api/health version")
require(api_health["config_loaded"] is True, "/api/health config")
require(api_health["mock_mode"] is True, "/api/health mock mode")
require(api_health["database"] == "ok", "/api/health database")
require(api_health["migration_version"] == 15, "/api/health migration")
require(api_health["collector"]["enabled"] is False, "collector disabled")
require(api_health["collector"]["connected"] is False, "collector disconnected")
require(
    api_health["mqtt_discovery"]["enabled"] is False,
    "MQTT Discovery disabled",
)
require(
    api_health["mqtt_discovery"]["connected"] is False,
    "MQTT Discovery disconnected",
)
require(api_health["topology"]["enabled"] is False, "topology disabled")
require(
    api_health["topology"]["manual_capture_enabled"] is False,
    "manual topology capture disabled",
)
require(
    api_health["topology"]["automatic_capture_enabled"] is False,
    "automatic topology capture disabled",
)
require(
    api_health["topology"]["capture_in_progress"] is False,
    "topology capture inactive",
)
require(api_health["topology"]["networks"] == [
    {
        "network_id": "docker-smoke",
        "network_name": "Docker smoke",
        "latest_snapshot": None,
    }
], "topology network has no captured snapshot")
require(storage["footprint"]["schema_version"] == 15, "storage schema")
require(
    storage["integrity"]["quick_check"]["status"] == "ok",
    "SQLite quick_check status",
)
require(
    storage["integrity"]["quick_check"]["violation_count"] == 0,
    "SQLite quick_check violations",
)
require(
    storage["integrity"]["foreign_key_check"]["status"] == "ok",
    "SQLite foreign-key status",
)
require(
    storage["integrity"]["foreign_key_check"]["violation_count"] == 0,
    "SQLite foreign-key violations",
)
require(config["version"] == expected_version, "config version")
require(config["data_mode"] == "mock", "config mock mode")
require(
    config["storage_path"] == "/data/zigbeelens.sqlite",
    "temporary storage path",
)
require(config["features"]["mqtt_collector"] is False, "config collector")
require(config["features"]["mqtt_discovery"] is False, "config Discovery")
require(
    config["features"]["device_payload_history"] is False,
    "config payload history",
)
require(
    config["features"]["manual_network_map"] is False,
    "config manual network map",
)
require(
    config["features"]["automatic_network_map"] is False,
    "config automatic network map",
)
require(
    config["mqtt_discovery"]["enabled"] is False,
    "config MQTT Discovery owner",
)
require(config["topology"]["enabled"] is False, "config topology")
require(config["topology"]["startup_scan"] is False, "config startup capture")
require(
    config["topology"]["refresh_interval_seconds"] == 0,
    "config periodic topology capture",
)
require(
    config["topology"]["manual_capture_enabled"] is False,
    "config manual capture",
)
require(
    config["topology"]["automatic_capture_enabled"] is False,
    "config automatic capture",
)
require(
    config["topology"]["capture_on_incident"] is False,
    "config incident capture",
)
require(config["configured_networks"] == [
    {
        "id": "docker-smoke",
        "name": "Docker smoke",
        "base_topic": "zigbeelens-docker-smoke-unused",
    }
], "synthetic network identity")
require(config["security"]["mode"] == "local", "trusted-local security")
require(
    config["security"]["api_token_configured"] is False,
    "no API token configured",
)
require(
    config["security"]["session_secret_configured"] is False,
    "no session secret configured",
)
ui_root = Path(ui_root_path).read_text(encoding="utf-8")
require("<title>ZigbeeLens</title>" in ui_root, "bundled UI identity")
PY

[[ -s "${DATA_DIR}/zigbeelens.sqlite" ]] ||
  fail "smoke database was not created in the external temporary data mount"
RUNNING="$(
  "${DOCKER_COMMAND}" inspect "${CONTAINER_ID}" --format '{{.State.Running}}'
)"
[[ "${RUNNING}" == "true" ]] || fail "Docker smoke container did not stay running"

if ! capture_container_log; then
  fail "unable to capture Docker smoke logs for external-activity checks"
fi
if LC_ALL=C grep -Eiq \
  "${FORBIDDEN_ACTIVITY_LOG_PATTERN}|${SENSITIVE_LOG_PATTERN}" \
  "${STATE_DIR}/container.log"
then
  print_safe_container_log
  fail "Docker smoke log contains forbidden external activity or sensitive output"
fi

FINAL_WORKTREE_STATUS="$(
  git -C "${ROOT}" status \
    --porcelain=v1 \
    --untracked-files=all \
    --ignore-submodules=none
)"
if [[ -n "${FINAL_WORKTREE_STATUS}" ]]; then
  echo "${FINAL_WORKTREE_STATUS}" >&2
  fail "Docker smoke changed the Git source tree"
fi

SMOKE_SUCCEEDED=1
