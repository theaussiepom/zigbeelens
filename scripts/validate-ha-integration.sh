#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HA_DIR="${ROOT}/apps/ha_integration"
ZC="${HA_DIR}/custom_components/zigbeelens"

echo "==> Validating ZigbeeLens HA integration layout"
test -f "${HA_DIR}/hacs.json"
test -f "${ZC}/manifest.json"
test -f "${ZC}/config_flow.py"
test -f "${ZC}/api.py"
test -f "${ZC}/compatibility.py"
test -f "${ZC}/coordinator.py"
test -f "${ZC}/panel_data.py"
test -f "${ZC}/sensor.py"
test -f "${ZC}/binary_sensor.py"
test -f "${ZC}/diagnostics.py"
test -f "${ZC}/repairs.py"
test -f "${ZC}/panel.py"
test -f "${ZC}/panel/zigbeelens-panel.js"
test -f "${ZC}/strings.json"
test -f "${ZC}/translations/en.json"
test -f "${ZC}/brand/icon.png"
test -f "${ZC}/brand/logo.png"
test -f "${ZC}/brand/icon@2x.png"
test -f "${ZC}/brand/logo@2x.png"

echo "==> Release version synchronisation"
python3 "${ROOT}/scripts/validate-release-version-sync.py"

echo "==> Panel JavaScript syntax"
node --check "${ZC}/panel/zigbeelens-panel.js"

echo "==> Packaging dry run"
bash "${ROOT}/scripts/package-hacs-repo.sh"
bash "${ROOT}/dist/zigbeelens-hacs/scripts/validate-hacs-repo.sh"
python3 "${ROOT}/scripts/validate-release-version-sync.py"

echo "==> Packaged Phase 5E source completeness"
for rel in \
  compatibility.py \
  panel_data.py \
  panel/zigbeelens-panel.js \
  strings.json \
  translations/en.json \
  repairs.py \
  diagnostics.py \
  api.py \
  coordinator.py
do
  src="${ZC}/${rel}"
  dst="${ROOT}/dist/zigbeelens-hacs/custom_components/zigbeelens/${rel}"
  test -f "${src}"
  test -f "${dst}"
  if [[ "${rel}" == *.py || "${rel}" == *.js || "${rel}" == *.json ]]; then
    # Manifest documentation URL is rewritten during packaging; skip exact compare.
    if [[ "${rel}" == "manifest.json" ]]; then
      continue
    fi
    # Translate/strings should match exactly.
    cmp -s "${src}" "${dst}" || {
      echo "FAIL: packaged file differs from source: ${rel}" >&2
      exit 1
    }
  fi
done
echo "OK: packaged Phase 5E critical sources match monorepo"

echo "==> Running HA integration tests"
python3 -m venv "${HA_DIR}/.venv-test"
# shellcheck disable=SC1091
source "${HA_DIR}/.venv-test/bin/activate"
pip install -q -r "${HA_DIR}/requirements-test.txt"
pytest -q "${HA_DIR}"

echo "HA integration validation passed."
