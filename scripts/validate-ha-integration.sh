#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HA_DIR="${ROOT}/apps/ha_integration"
ZC="${HA_DIR}/custom_components/zigbeelens"
SKIP_MATRIX=0

if [[ "${1:-}" == "--skip-matrix" ]]; then
  SKIP_MATRIX=1
  shift
fi
if [[ "$#" -ne 0 ]]; then
  echo "Usage: $0 [--skip-matrix]" >&2
  exit 2
fi

echo "==> Validating ZigbeeLens HA integration layout"
test -f "${HA_DIR}/hacs.json"
test -f "${HA_DIR}/ha-test-matrix.json"
test -f "${HA_DIR}/requirements-test.txt"
test -f "${HA_DIR}/requirements-test-minimum.txt"
test -f "${HA_DIR}/requirements-test-current.txt"
test -x "${ROOT}/scripts/test-ha-integration-matrix.sh"
test -f "${ZC}/manifest.json"
test -f "${ZC}/config_flow.py"
test -f "${ZC}/api.py"
test -f "${ZC}/compatibility.py"
test -f "${ZC}/coordinator.py"
test -f "${ZC}/panel_data.py"
test -f "${ZC}/sensor.py"
test -f "${ZC}/binary_sensor.py"
test -f "${ZC}/diagnostics.py"
test -f "${ZC}/enrichment_manager.py"
test -f "${ZC}/ha_enrichment.py"
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
  coordinator.py \
  enrichment_manager.py \
  ha_enrichment.py
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

if [[ "${SKIP_MATRIX}" -eq 0 ]]; then
  echo "==> Running exact Home Assistant integration matrix"
  bash "${ROOT}/scripts/test-ha-integration-matrix.sh"
else
  echo "==> Exact Home Assistant integration matrix is owned by separate CI jobs"
fi

echo "HA integration validation passed."
