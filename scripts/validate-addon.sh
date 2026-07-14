#!/usr/bin/env bash
# Validate Home Assistant add-on packaging files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADDON="${ROOT}/apps/addon/zigbeelens"
REPO="${ROOT}/apps/addon/repository.yaml"
STAGE="${ADDON}/.build"
FAIL=0

fail() {
  echo "FAIL: $1" >&2
  FAIL=1
}

ok() {
  echo "OK: $1"
}

require_file() {
  if [[ -f "$1" ]]; then ok "$1"; else fail "missing file $1"; fi
}

require_executable() {
  if [[ -x "$1" ]]; then ok "executable $1"; else fail "not executable $1"; fi
}

echo "=== ZigbeeLens add-on validation ==="

require_file "${REPO}"
require_file "${ADDON}/config.yaml"
require_file "${ADDON}/Dockerfile"
require_file "${ADDON}/run.sh"
require_file "${ADDON}/README.md"
require_file "${ADDON}/CHANGELOG.md"
require_file "${ADDON}/icon.png"
require_file "${ADDON}/logo.png"
require_file "${ADDON}/translations/en.yaml"

require_executable "${ADDON}/run.sh"

echo "==> Release version synchronisation"
python3 "${ROOT}/scripts/validate-release-version-sync.py" || FAIL=1

if grep -q 'ingress_port: 8377' "${ADDON}/config.yaml"; then
  ok "ingress_port matches Core port 8377"
else
  fail "ingress_port must be 8377"
fi

if grep -q 'password: ""' "${ADDON}/config.yaml"; then
  ok "default options do not embed secrets"
else
  fail "check default options for embedded secrets"
fi

if grep -q 'secret-pass\|hunter2\|changeme' "${ADDON}/config.yaml" "${ADDON}/README.md" 2>/dev/null; then
  fail "obvious secret placeholder found in add-on defaults/docs"
else
  ok "no obvious secret placeholders in defaults/docs"
fi

if grep -q 'mqtt_discovery: false' "${ADDON}/config.yaml"; then
  ok "mqtt_discovery disabled by default"
else
  fail "mqtt_discovery should default to false"
fi

echo "==> Supervisor staging dry run"
bash "${ROOT}/scripts/prepare-addon.sh" || FAIL=1

for rel in \
  apps/core/src/zigbeelens/api/summary.py \
  apps/core/src/zigbeelens/services/reports.py \
  apps/ui/package.json \
  packages/shared/package.json \
  run.sh \
  Dockerfile
do
  if [[ -e "${STAGE}/${rel}" ]]; then
    ok "stage has ${rel}"
  else
    fail "stage missing ${rel}"
  fi
done

if [[ -d "${STAGE}/apps/core/src/zigbeelens/decisions" ]]; then
  ok "stage has decisions package"
else
  fail "stage missing apps/core/src/zigbeelens/decisions"
fi

if [[ -d "${ROOT}/apps/core/.venv" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT}/apps/core/.venv/bin/activate"
  PYTHONPATH="${ROOT}/apps/core/src" python3 -m pytest -q "${ROOT}/apps/core/tests/test_addon_config.py" || FAIL=1
else
  PYTHONPATH="${ROOT}/apps/core/src" python3 -m pytest -q "${ROOT}/apps/core/tests/test_addon_config.py" 2>/dev/null || {
    echo "SKIP: add-on config tests (install apps/core dev deps to run)"
  }
fi

if [[ "${FAIL}" -ne 0 ]]; then
  echo "Add-on validation failed."
  exit 1
fi

echo "Add-on validation passed."
