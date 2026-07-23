#!/usr/bin/env bash
# Stage HACS install repository (custom_components at repo root).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/apps/ha_integration"
DIST="${ROOT}/dist/zigbeelens-hacs"
OWNER="${GITHUB_OWNER:-theaussiepom}"
README_IN="${ROOT}/release/zigbeelens-hacs/README.md.in"

rm -rf "${DIST}"
mkdir -p "${DIST}/custom_components"

cp -R "${SRC}/custom_components/zigbeelens" "${DIST}/custom_components/"
find "${DIST}" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
cp "${ROOT}/LICENSE" "${DIST}/"
cp "${ROOT}/CHANGELOG.md" "${DIST}/"

cat > "${DIST}/hacs.json" <<EOF
{
  "name": "ZigbeeLens",
  "content_in_root": false,
  "render_readme": true,
  "homeassistant": "2025.1.0"
}
EOF

if [[ ! -f "${README_IN}" ]]; then
  echo "FAIL: missing ${README_IN}" >&2
  exit 1
fi
sed "s|@GITHUB_OWNER@|${OWNER}|g" "${README_IN}" > "${DIST}/README.md"

python3 - <<PY
import json
from pathlib import Path

manifest = Path("${DIST}/custom_components/zigbeelens/manifest.json")
data = json.loads(manifest.read_text())
data["documentation"] = "https://github.com/${OWNER}/zigbeelens-hacs"
data["issue_tracker"] = "https://github.com/${OWNER}/zigbeelens/issues"
manifest.write_text(json.dumps(data, indent=2) + "\n")
PY

mkdir -p "${DIST}/.github/workflows" "${DIST}/scripts"
cp "${ROOT}/release/zigbeelens-hacs/.github/workflows/ci.yml" "${DIST}/.github/workflows/ci.yml"
cp "${ROOT}/release/zigbeelens-hacs/.github/workflows/release.yml" "${DIST}/.github/workflows/release.yml"
cp "${ROOT}/release/zigbeelens-hacs/scripts/validate-hacs-repo.sh" "${DIST}/scripts/validate-hacs-repo.sh"
chmod +x "${DIST}/scripts/validate-hacs-repo.sh"

echo "Packaged HACS repo at ${DIST}"
find "${DIST}" -type f | sort
