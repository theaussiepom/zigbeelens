#!/usr/bin/env bash
set -euo pipefail

OPTIONS_FILE="${OPTIONS_FILE:-/data/options.json}"
CONFIG_DIR="/data/zigbeelens"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"
SECRETS_DIR="${CONFIG_DIR}/secrets"
API_TOKEN_FILE="${SECRETS_DIR}/api_token"

if [[ ! -f "$OPTIONS_FILE" ]]; then
  echo "ERROR: Missing add-on options at ${OPTIONS_FILE}" >&2
  exit 1
fi

mkdir -p "$CONFIG_DIR"

export OPTIONS_FILE CONFIG_FILE SECRETS_DIR API_TOKEN_FILE

python3 - <<'PY'
import json
import os
from pathlib import Path

from zigbeelens.config.addon import (
    install_optional_api_token_file,
    options_to_yaml,
    safe_startup_log_lines,
)

options_path = Path(os.environ["OPTIONS_FILE"])
config_path = Path(os.environ["CONFIG_FILE"])
secrets_dir = Path(os.environ["SECRETS_DIR"])
token_file = Path(os.environ["API_TOKEN_FILE"])
options = json.loads(options_path.read_text(encoding="utf-8"))
config_path.write_text(options_to_yaml(options), encoding="utf-8")
bearer_active = install_optional_api_token_file(
    options,
    secrets_dir=secrets_dir,
    token_file=token_file,
)
for line in safe_startup_log_lines(
    options,
    bearer_fallback_configured=bearer_active,
):
    print(line, flush=True)
PY

# Export token-file path for the Core process when the optional bearer is active.
if [[ -f "$API_TOKEN_FILE" ]]; then
  export ZIGBEELENS_SECURITY_API_TOKEN_FILE="$API_TOKEN_FILE"
else
  unset ZIGBEELENS_SECURITY_API_TOKEN_FILE || true
fi

export ZIGBEELENS_CONFIG="$CONFIG_FILE"
export ZIGBEELENS_STATIC_DIR="${ZIGBEELENS_STATIC_DIR:-/app/static}"

# Bind comes from the generated AppConfig (explicit 0.0.0.0), not a shell override.
exec zigbeelens
