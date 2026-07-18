#!/usr/bin/env bash
set -euo pipefail

# HA add-on mode: /data/options.json → generated config
OPTIONS_FILE="${OPTIONS_FILE:-/data/options.json}"
CONFIG_DIR="/data/zigbeelens"
HA_CONFIG="${CONFIG_DIR}/config.yaml"

if [[ -f "${OPTIONS_FILE}" ]]; then
  mkdir -p "${CONFIG_DIR}"
  export OPTIONS_FILE CONFIG_FILE="${HA_CONFIG}"
  python3 - <<'PY'
import json
import os
from pathlib import Path

from zigbeelens.config.addon import options_to_yaml, safe_startup_log_lines

options_path = Path(os.environ["OPTIONS_FILE"])
config_path = Path(os.environ["CONFIG_FILE"])
options = json.loads(options_path.read_text(encoding="utf-8"))
config_path.write_text(options_to_yaml(options), encoding="utf-8")
for line in safe_startup_log_lines(options):
    print(line, flush=True)
PY
  export ZIGBEELENS_CONFIG="${HA_CONFIG}"
elif [[ -n "${ZIGBEELENS_CONFIG:-}" && -f "${ZIGBEELENS_CONFIG}" ]]; then
  : # standalone: config already mounted
elif [[ -f /config/config.yaml ]]; then
  export ZIGBEELENS_CONFIG="/config/config.yaml"
else
  echo "ERROR: No configuration found." >&2
  echo "  HA add-on: expected ${OPTIONS_FILE}" >&2
  echo "  Docker: mount config at /config/config.yaml or set ZIGBEELENS_CONFIG" >&2
  exit 1
fi

export ZIGBEELENS_STATIC_DIR="${ZIGBEELENS_STATIC_DIR:-/app/static}"
mkdir -p /data "$(dirname "${ZIGBEELENS_CONFIG}")"

# Optional compatibility override resolved into AppConfig by the zigbeelens launcher.
# Do not pass a separate --host/--port that can disagree with typed config.
if [[ -n "${ZIGBEELENS_PORT:-}" ]]; then
  echo "ZigbeeLens starting (config=${ZIGBEELENS_CONFIG}, ZIGBEELENS_PORT=${ZIGBEELENS_PORT})"
else
  echo "ZigbeeLens starting (config=${ZIGBEELENS_CONFIG})"
fi

exec zigbeelens
