#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HA_DIR="${ROOT}/apps/ha_integration"

echo "==> Validating ZigbeeLens HA integration layout"
test -f "${HA_DIR}/hacs.json"
test -f "${HA_DIR}/custom_components/zigbeelens/manifest.json"
test -f "${HA_DIR}/custom_components/zigbeelens/config_flow.py"
test -f "${HA_DIR}/custom_components/zigbeelens/api.py"
test -f "${HA_DIR}/custom_components/zigbeelens/coordinator.py"
test -f "${HA_DIR}/custom_components/zigbeelens/sensor.py"
test -f "${HA_DIR}/custom_components/zigbeelens/binary_sensor.py"
test -f "${HA_DIR}/custom_components/zigbeelens/diagnostics.py"
test -f "${HA_DIR}/custom_components/zigbeelens/repairs.py"
test -f "${HA_DIR}/custom_components/zigbeelens/panel.py"
test -f "${HA_DIR}/custom_components/zigbeelens/brand/icon.png"
test -f "${HA_DIR}/custom_components/zigbeelens/brand/logo.png"
test -f "${HA_DIR}/custom_components/zigbeelens/brand/icon@2x.png"
test -f "${HA_DIR}/custom_components/zigbeelens/brand/logo@2x.png"

echo "==> Packaging dry run"
bash "${ROOT}/scripts/package-hacs.sh"

echo "==> Running HA integration tests"
python3 -m venv "${HA_DIR}/.venv-test"
source "${HA_DIR}/.venv-test/bin/activate"
pip install -q -r "${HA_DIR}/requirements-test.txt"
pytest -q "${HA_DIR}"

echo "HA integration validation passed."
