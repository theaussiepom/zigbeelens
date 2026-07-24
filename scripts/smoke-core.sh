#!/usr/bin/env bash
# Hermetic Core smoke: isolated config/database, no pip or repository runtime data.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR=""
CORE_PID_PATH=""
CORE_PID=""
CORE_RUNNER_PID=""

capture_core_pid() {
  if [[ -n "$CORE_PID" ]]; then
    return 0
  fi
  if [[ -z "$CORE_PID_PATH" || ! -f "$CORE_PID_PATH" ]]; then
    return 1
  fi
  local candidate
  IFS= read -r candidate <"$CORE_PID_PATH" || return 1
  if [[ ! "$candidate" =~ ^[0-9]+$ ]] || (( candidate <= 1 )) || (( candidate == $$ )); then
    return 1
  fi
  CORE_PID="$candidate"
}

terminate_pid() {
  local pid="$1"
  if [[ -z "$pid" || ! "$pid" =~ ^[0-9]+$ ]] || (( pid <= 1 )) || (( pid == $$ )); then
    return
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    return
  fi
  kill "$pid" 2>/dev/null || true
  for _attempt in {1..50}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      return
    fi
    sleep 0.1
  done
  kill -KILL "$pid" 2>/dev/null || true
}

cleanup() {
  capture_core_pid 2>/dev/null || true
  terminate_pid "$CORE_PID"
  if [[ "$CORE_RUNNER_PID" != "$CORE_PID" ]]; then
    for _attempt in {1..100}; do
      if [[ -z "$CORE_RUNNER_PID" ]] || ! kill -0 "$CORE_RUNNER_PID" 2>/dev/null; then
        break
      fi
      sleep 0.01
    done
    terminate_pid "$CORE_RUNNER_PID"
  fi
  if [[ -n "$CORE_RUNNER_PID" ]]; then
    wait "$CORE_RUNNER_PID" 2>/dev/null || true
  fi
  if [[ -n "$CORE_PID" && "$CORE_RUNNER_PID" != "$CORE_PID" ]]; then
    for _attempt in {1..100}; do
      if ! kill -0 "$CORE_PID" 2>/dev/null; then
        break
      fi
      sleep 0.01
    done
  fi
  if [[ -n "$STATE_DIR" && -d "$STATE_DIR" ]]; then
    rm -rf "$STATE_DIR"
  fi
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

print_core_log() {
  if [[ -n "$STATE_DIR" && -f "$STATE_DIR/core.log" ]]; then
    echo "=== smoke-core: safe Core log ===" >&2
    sed -n '1,240p' "$STATE_DIR/core.log" >&2
  fi
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cd "$ROOT"
export PYTHONPATH="$ROOT/apps/core/src"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1

# Neutralize interpreter/project selectors that can redirect or disable the
# verified command. Cache/index/certificate settings remain available to uv.
unset PYTHONHOME
unset PYTHONINSPECT
unset PYTHONSTARTUP
unset VIRTUAL_ENV
unset UV_ACTIVE
unset UV_CONFIG_FILE
unset UV_ENV_FILE
unset UV_FROZEN
unset UV_MANAGED_PYTHON
unset UV_NO_BUILD
unset UV_NO_BUILD_ISOLATION
unset UV_NO_DEFAULT_GROUPS
unset UV_NO_DEV
unset UV_NO_INSTALL_PACKAGE
unset UV_NO_INSTALL_PROJECT
unset UV_NO_INSTALL_WORKSPACE
unset UV_NO_MANAGED_PYTHON
unset UV_NO_PROJECT
unset UV_NO_SYNC
unset UV_OFFLINE
unset UV_ONLY_GROUP
unset UV_PROJECT
unset UV_PROJECT_ENVIRONMENT
unset UV_PYTHON
unset UV_PYTHON_DOWNLOADS
unset UV_WORKING_DIR

CORE_COMMAND=()
PYTHON_OWNER=""

if [[ -n "${ZIGBEELENS_CORE_PYTHON:-}" ]]; then
  if [[ ! -x "$ZIGBEELENS_CORE_PYTHON" ]]; then
    fail "explicit Core Python is not executable: $ZIGBEELENS_CORE_PYTHON"
  fi
  CORE_COMMAND=("$ZIGBEELENS_CORE_PYTHON")
  PYTHON_OWNER="explicit"
elif UV_COMMAND="$(command -v uv 2>/dev/null)" && [[ -n "$UV_COMMAND" ]]; then
  CORE_COMMAND=(
    "$UV_COMMAND" run
    --isolated
    --locked
    --no-config
    --no-env-file
    --project "$ROOT/apps/core"
    --extra dev
    python
  )
  PYTHON_OWNER="uv"
elif PYTHON3_COMMAND="$(command -v python3 2>/dev/null)" && [[ -n "$PYTHON3_COMMAND" ]]; then
  CORE_COMMAND=("$PYTHON3_COMMAND")
  PYTHON_OWNER="python3"
else
  fail "no Core Python is available (set ZIGBEELENS_CORE_PYTHON or install uv)"
fi

if ! PROBE_RESULT="$("${CORE_COMMAND[@]}" - "$ROOT/apps/core/src" 2>/dev/null <<'PY'
import sys
from pathlib import Path

import uvicorn
import zigbeelens
import zigbeelens.main

source_root = Path(sys.argv[1]).resolve()
module_path = Path(zigbeelens.__file__).resolve()
try:
    module_path.relative_to(source_root)
except ValueError:
    raise SystemExit(1)
print("zigbeelens-core-smoke-python-ok")
PY
)"; then
  fail "$PYTHON_OWNER Core Python cannot import this checkout and uvicorn"
fi
if [[ "$PROBE_RESULT" != "zigbeelens-core-smoke-python-ok" ]]; then
  fail "$PYTHON_OWNER Core Python did not complete the checkout import probe"
fi
echo "Core smoke Python owner: $PYTHON_OWNER"

STATE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/zigbeelens-core-smoke.XXXXXX")"
CONFIG_PATH="$STATE_DIR/config.yaml"
DATABASE_PATH="$STATE_DIR/zigbeelens.sqlite"
LOG_PATH="$STATE_DIR/core.log"
HEALTH_STATUS_PATH="$STATE_DIR/health.json"
STORAGE_STATUS_PATH="$STATE_DIR/storage-status.json"
CORE_PID_PATH="$STATE_DIR/core.pid"

if [[ -n "${SMOKE_PORT:-}" ]]; then
  if [[ ! "$SMOKE_PORT" =~ ^[0-9]{1,5}$ ]]; then
    fail "SMOKE_PORT must be an integer between 1 and 65535"
  fi
  PORT=$((10#$SMOKE_PORT))
  if (( PORT < 1 || PORT > 65535 )); then
    fail "SMOKE_PORT must be an integer between 1 and 65535"
  fi
  if ! "${CORE_COMMAND[@]}" - "$PORT" >/dev/null 2>&1 <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.bind(("127.0.0.1", port))
PY
  then
    fail "Core smoke port is unavailable: 127.0.0.1:$PORT"
  fi
else
  PORT="$("${CORE_COMMAND[@]}" - <<'PY'
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.bind(("127.0.0.1", 0))
    print(probe.getsockname()[1])
PY
  )"
fi

"${CORE_COMMAND[@]}" - "$CONFIG_PATH" "$DATABASE_PATH" "$PORT" <<'PY'
import json
import sys
from pathlib import Path

config_path, database_path, raw_port = sys.argv[1:]
config = {
    "server": {"host": "127.0.0.1", "port": int(raw_port)},
    "mode": {"mock": True},
    "security": {"mode": "local"},
    "mqtt": {
        "server": "",
        "username": "",
        "password": "",
        "client_id": "zigbeelens-smoke",
        "tls": {"enabled": False, "reject_unauthorized": True},
    },
    "networks": [
        {
            "id": "smoke",
            "name": "Smoke",
            "base_topic": "zigbeelens-smoke-unused",
        }
    ],
    "storage": {
        "path": database_path,
        "retention_days": 1,
        "resolved_incident_retention_days": 1,
        "maintenance_interval_hours": 24,
    },
    "features": {
        "mqtt_collector": False,
        "mqtt_discovery": False,
        "bridge_logs": False,
        "device_payload_history": False,
        "manual_network_map": False,
        "automatic_network_map": False,
    },
    "mqtt_discovery": {"enabled": False},
    "topology": {
        "enabled": False,
        "manual_capture_enabled": False,
        "automatic_capture_enabled": False,
        "startup_scan": False,
        "refresh_interval_seconds": 0,
        "capture_on_incident": False,
    },
}
Path(config_path).write_text(
    json.dumps(config, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

# Do not inherit credentials, deployment config, or broker overrides.
unset ZIGBEELENS_API_KEY
unset ZIGBEELENS_MOCK_SCENARIO
unset ZIGBEELENS_MQTT_PASSWORD
unset ZIGBEELENS_MQTT_PASSWORD_FILE
unset ZIGBEELENS_MQTT_USERNAME
unset ZIGBEELENS_OPENAPI_ENABLED
unset ZIGBEELENS_SECURITY_API_TOKEN
unset ZIGBEELENS_SECURITY_API_TOKEN_FILE
unset ZIGBEELENS_SECURITY_MODE
unset ZIGBEELENS_SECURITY_SESSION_SECRET
unset ZIGBEELENS_SECURITY_SESSION_SECRET_FILE
unset ZIGBEELENS_STATIC_DIR
export ZIGBEELENS_CONFIG="$CONFIG_PATH"
export ZIGBEELENS_PORT="$PORT"

BASE="http://127.0.0.1:$PORT"
curl_smoke() {
  curl \
    --fail \
    --silent \
    --show-error \
    --noproxy '*' \
    --connect-timeout 2 \
    --max-time 5 \
    "$@"
}

echo "=== smoke-core: starting isolated Core on port $PORT ==="
"${CORE_COMMAND[@]}" - "$CORE_PID_PATH" "$PORT" >"$LOG_PATH" 2>&1 <<'PY' &
import os
import sys
from pathlib import Path

pid_path = Path(sys.argv[1])
pending_path = pid_path.with_name(f"{pid_path.name}.tmp")
pending_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
os.replace(pending_path, pid_path)
os.execv(
    sys.executable,
    [
        sys.executable,
        "-m",
        "uvicorn",
        "zigbeelens.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        sys.argv[2],
    ],
)
PY
CORE_RUNNER_PID=$!

for _attempt in {1..150}; do
  if capture_core_pid; then
    break
  fi
  if ! kill -0 "$CORE_RUNNER_PID" 2>/dev/null; then
    wait "$CORE_RUNNER_PID" 2>/dev/null || true
    CORE_RUNNER_PID=""
    print_core_log
    fail "Core exited before publishing its process identity"
  fi
  sleep 0.1
done
if [[ -z "$CORE_PID" ]]; then
  print_core_log
  fail "Core did not publish its process identity"
fi

READY=false
for _attempt in {1..100}; do
  if curl_smoke "$BASE/healthz" >/dev/null 2>&1; then
    READY=true
    break
  fi
  if ! kill -0 "$CORE_PID" 2>/dev/null || ! kill -0 "$CORE_RUNNER_PID" 2>/dev/null; then
    wait "$CORE_RUNNER_PID" 2>/dev/null || true
    CORE_RUNNER_PID=""
    print_core_log
    fail "Core exited before readiness"
  fi
  sleep 0.1
done
if [[ "$READY" != "true" ]]; then
  print_core_log
  fail "Core did not become ready"
fi

echo "Checking /healthz..."
curl_smoke "$BASE/healthz" |
  grep -q '"status":"ok"' || fail "/healthz did not report ok"

echo "Checking /api/health isolation..."
curl_smoke --output "$HEALTH_STATUS_PATH" "$BASE/api/health"
"${CORE_COMMAND[@]}" - "$HEALTH_STATUS_PATH" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "status": "ok",
    "version": "0.1.14",
    "config_loaded": True,
    "mock_mode": True,
    "database": "ok",
    "migration_version": 14,
}
for key, value in expected.items():
    if payload.get(key) != value:
        raise SystemExit(f"unexpected /api/health {key}")
if payload.get("collector", {}).get("enabled") is not False:
    raise SystemExit("MQTT collector is not disabled")
if payload.get("mqtt_discovery", {}).get("enabled") is not False:
    raise SystemExit("MQTT Discovery is not disabled")
topology = payload.get("topology", {})
for key in ("enabled", "manual_capture_enabled", "automatic_capture_enabled"):
    if topology.get(key) is not False:
        raise SystemExit(f"topology {key} is not disabled")
PY

echo "Checking /api/dashboard..."
curl_smoke "$BASE/api/dashboard" |
  grep -q '"decision_summary"' || fail "/api/dashboard contract mismatch"

echo "Checking /api/version..."
curl_smoke "$BASE/api/version" |
  grep -q '"version":"0.1.14"' || fail "/api/version contract mismatch"

echo "Checking / (bundled UI root or Core fallback)..."
ROOT_CODE="$(
  curl_smoke \
    --output /dev/null \
    --write-out '%{http_code}' \
    "$BASE/"
)"
[[ "$ROOT_CODE" == "200" ]] || fail "/ returned $ROOT_CODE"

echo "Checking isolated storage..."
[[ -s "$DATABASE_PATH" ]] || fail "temporary SQLite database was not created"
curl_smoke \
  --output "$STORAGE_STATUS_PATH" \
  "$BASE/api/storage/status"
"${CORE_COMMAND[@]}" - "$STORAGE_STATUS_PATH" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("footprint", {}).get("schema_version") != 14:
    raise SystemExit("temporary database schema is not version 14")
integrity = payload.get("integrity", {})
for key in ("quick_check", "foreign_key_check"):
    fact = integrity.get(key, {})
    if fact.get("status") != "ok" or fact.get("violation_count") != 0:
        raise SystemExit(f"temporary database {key} was not accepted")
PY

if grep -Eiq \
  'MQTT discovery failed|MQTT collector failed|socket\.gaierror|ConnectionRefusedError|getaddrinfo' \
  "$LOG_PATH"; then
  print_core_log
  fail "Core attempted an MQTT or Discovery connection"
fi

echo "OK: smoke-core passed (schema=14, isolated_state=true, mqtt_attempts=0)"
