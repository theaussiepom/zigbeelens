#!/usr/bin/env bash
set -euo pipefail

OPTIONS_FILE="${OPTIONS_FILE:-/data/options.json}"
CONFIG_DIR="/data/zigbeelens"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"

if [[ ! -f "$OPTIONS_FILE" ]]; then
  echo "ERROR: Missing add-on options at ${OPTIONS_FILE}" >&2
  exit 1
fi

mkdir -p "$CONFIG_DIR"

export OPTIONS_FILE CONFIG_FILE

python3 - <<'PY'
import json
import os
import sys
from pathlib import Path

from zigbeelens.config.addon import options_to_yaml, safe_startup_log_lines

options_path = Path(os.environ["OPTIONS_FILE"])
config_path = Path(os.environ["CONFIG_FILE"])
options = json.loads(options_path.read_text(encoding="utf-8"))
config_path.write_text(options_to_yaml(options), encoding="utf-8")
for line in safe_startup_log_lines(options):
    print(line, flush=True)
PY

export ZIGBEELENS_CONFIG="$CONFIG_FILE"
export ZIGBEELENS_STATIC_DIR="${ZIGBEELENS_STATIC_DIR:-/app/static}"

exec uvicorn zigbeelens.main:app --host 0.0.0.0 --port 8377
