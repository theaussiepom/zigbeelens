#!/usr/bin/env bash
# Stage HACS install repository (custom_components at repo root).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${ROOT}/dist/zigbeelens-hacs"
SOURCE_REPOSITORY="${ZIGBEELENS_SOURCE_REPOSITORY-theaussiepom/zigbeelens}"
FUTURE_HACS_REPOSITORY="${ZIGBEELENS_FUTURE_HACS_REPOSITORY-theaussiepom/zigbeelens-hacs}"
REVIEWED_HACS_REPOSITORY="theaussiepom/zigbeelens-hacs"

PACKAGE_INPUTS=(
  apps/ha_integration/custom_components/zigbeelens
  apps/ha_integration/docs
  apps/ha_integration/tests
  apps/ha_integration/ha-test-matrix.json
  apps/ha_integration/pytest.ini
  apps/ha_integration/requirements-test.txt
  apps/ha_integration/requirements-test-minimum.txt
  apps/ha_integration/requirements-test-current.txt
  apps/core/tests/fixtures/http_origin_vectors.json
  LICENSE
  CHANGELOG.md
  release/zigbeelens-hacs/README.md.in
  release/zigbeelens-hacs/.github/workflows
  release/zigbeelens-hacs/scripts/validate-hacs-repo.sh
  scripts/package-hacs-repo.sh
  scripts/test-ha-integration-matrix.sh
)

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

validate_repository_identifier() {
  local variable_name="$1"
  local value="$2"
  local repository="${value#*/}"
  if [[ ! "${value}" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}$ ]] ||
    [[ "${repository}" == "." ]] || [[ "${repository}" == ".." ]]
  then
    fail "${variable_name} must be an exact owner/repository identifier"
  fi
}

if [[ -n "${GITHUB_OWNER+x}" ]]; then
  fail "GITHUB_OWNER is no longer supported; use ZIGBEELENS_SOURCE_REPOSITORY and ZIGBEELENS_FUTURE_HACS_REPOSITORY"
fi
validate_repository_identifier \
  "ZIGBEELENS_SOURCE_REPOSITORY" "${SOURCE_REPOSITORY}"
validate_repository_identifier \
  "ZIGBEELENS_FUTURE_HACS_REPOSITORY" "${FUTURE_HACS_REPOSITORY}"
validate_repository_identifier \
  "reviewed HACS repository" "${REVIEWED_HACS_REPOSITORY}"

if ! GIT_TOPLEVEL="$(
  git -C "${ROOT}" rev-parse --show-toplevel 2>/dev/null
)"; then
  fail "package source root must be the exact root of a Git checkout"
fi
if [[ "${GIT_TOPLEVEL}" != "${ROOT}" ]]; then
  fail "package source root must be the exact root of a Git checkout"
fi
if ! HEAD_COMMIT="$(
  git -C "${ROOT}" rev-parse --verify 'HEAD^{commit}' 2>/dev/null
)"; then
  fail "unable to resolve the checked-out Git HEAD commit"
fi

if [[ -n "${ZIGBEELENS_SOURCE_COMMIT+x}" ]]; then
  SOURCE_COMMIT_INPUT="${ZIGBEELENS_SOURCE_COMMIT}"
else
  SOURCE_COMMIT_INPUT="${HEAD_COMMIT}"
fi
SOURCE_COMMIT_VALUE="$(
  printf '%s' "${SOURCE_COMMIT_INPUT}" | tr '[:upper:]' '[:lower:]'
)"
if [[ "${#SOURCE_COMMIT_VALUE}" -ne 40 ]] || [[ "${SOURCE_COMMIT_VALUE}" == *[!0-9a-f]* ]]; then
  fail "ZIGBEELENS_SOURCE_COMMIT must be exactly 40 hexadecimal characters after lowercase normalization"
fi
if ! git -C "${ROOT}" cat-file -e "${SOURCE_COMMIT_VALUE}^{commit}" 2>/dev/null; then
  fail "ZIGBEELENS_SOURCE_COMMIT does not identify an existing commit"
fi
if [[ "${SOURCE_COMMIT_VALUE}" != "${HEAD_COMMIT}" ]]; then
  fail "ZIGBEELENS_SOURCE_COMMIT does not match checked-out HEAD"
fi

if ! git -C "${ROOT}" diff --quiet \
  "${SOURCE_COMMIT_VALUE}" -- "${PACKAGE_INPUTS[@]}"
then
  echo "FAIL: tracked package inputs differ from SOURCE_COMMIT:" >&2
  git -C "${ROOT}" diff --name-status \
    "${SOURCE_COMMIT_VALUE}" -- "${PACKAGE_INPUTS[@]}" >&2
  exit 1
fi
UNTRACKED_INPUTS="$(
  git -C "${ROOT}" ls-files --others --exclude-standard \
    -- "${PACKAGE_INPUTS[@]}"
)"
if [[ -n "${UNTRACKED_INPUTS}" ]]; then
  echo "FAIL: untracked package inputs are not present in SOURCE_COMMIT:" >&2
  printf '%s\n' "${UNTRACKED_INPUTS}" >&2
  exit 1
fi

SOURCE_SNAPSHOT="$(mktemp -d)"
cleanup_source_snapshot() {
  rm -rf "${SOURCE_SNAPSHOT}"
}
trap cleanup_source_snapshot EXIT

if ! git -C "${ROOT}" archive \
  --format=tar "${SOURCE_COMMIT_VALUE}" -- "${PACKAGE_INPUTS[@]}" |
  tar -xf - -C "${SOURCE_SNAPSHOT}"
then
  fail "unable to extract package inputs from SOURCE_COMMIT"
fi

SRC="${SOURCE_SNAPSHOT}/apps/ha_integration"
README_IN="${SOURCE_SNAPSHOT}/release/zigbeelens-hacs/README.md.in"
if [[ ! -f "${README_IN}" ]]; then
  fail "SOURCE_COMMIT is missing release/zigbeelens-hacs/README.md.in"
fi

rm -rf "${DIST}"
mkdir -p "${DIST}/custom_components"
printf '%s\n' "${SOURCE_COMMIT_VALUE}" > "${DIST}/SOURCE_COMMIT"

cp -R "${SRC}/custom_components/zigbeelens" "${DIST}/custom_components/"
cp -R "${SRC}/docs" "${DIST}/docs"
cp -R "${SRC}/tests" "${DIST}/tests"
mkdir -p "${DIST}/tests/fixtures"
cp \
  "${SOURCE_SNAPSHOT}/apps/core/tests/fixtures/http_origin_vectors.json" \
  "${DIST}/tests/fixtures/"
cp "${SRC}/ha-test-matrix.json" "${DIST}/"
cp "${SRC}/pytest.ini" "${DIST}/"
cp "${SRC}/requirements-test.txt" "${DIST}/"
cp "${SRC}/requirements-test-minimum.txt" "${DIST}/"
cp "${SRC}/requirements-test-current.txt" "${DIST}/"
cp "${SOURCE_SNAPSHOT}/LICENSE" "${DIST}/"
cp "${SOURCE_SNAPSHOT}/CHANGELOG.md" "${DIST}/"

cat > "${DIST}/hacs.json" <<EOF
{
  "name": "ZigbeeLens",
  "content_in_root": false,
  "render_readme": true,
  "homeassistant": "2025.1.0"
}
EOF

sed \
  -e "s|@SOURCE_REPOSITORY@|${SOURCE_REPOSITORY}|g" \
  -e "s|@FUTURE_HACS_REPOSITORY@|${FUTURE_HACS_REPOSITORY}|g" \
  -e "s|@REVIEWED_HACS_REPOSITORY@|${REVIEWED_HACS_REPOSITORY}|g" \
  -e "s|@SOURCE_COMMIT@|${SOURCE_COMMIT_VALUE}|g" \
  "${README_IN}" > "${DIST}/README.md"

python3 - <<PY
import json
from pathlib import Path

manifest = Path("${DIST}/custom_components/zigbeelens/manifest.json")
data = json.loads(manifest.read_text())
data["documentation"] = "https://github.com/${SOURCE_REPOSITORY}/blob/${SOURCE_COMMIT_VALUE}/docs/hacs.md"
data["issue_tracker"] = "https://github.com/${SOURCE_REPOSITORY}/issues"
manifest.write_text(json.dumps(data, indent=2) + "\n")
PY

mkdir -p "${DIST}/.github/workflows" "${DIST}/scripts"
cp "${SOURCE_SNAPSHOT}/release/zigbeelens-hacs/.github/workflows/ci.yml" \
  "${DIST}/.github/workflows/ci.yml"
cp "${SOURCE_SNAPSHOT}/release/zigbeelens-hacs/.github/workflows/release.yml" \
  "${DIST}/.github/workflows/release.yml"
cp "${SOURCE_SNAPSHOT}/release/zigbeelens-hacs/scripts/validate-hacs-repo.sh" \
  "${DIST}/scripts/validate-hacs-repo.sh"
cp "${SOURCE_SNAPSHOT}/scripts/test-ha-integration-matrix.sh" \
  "${DIST}/scripts/test-ha-integration-matrix.sh"
chmod +x "${DIST}/scripts/validate-hacs-repo.sh"
chmod +x "${DIST}/scripts/test-ha-integration-matrix.sh"

echo "Packaged HACS repo at ${DIST}"
find "${DIST}" -type f | sort
