#!/usr/bin/env bash
# Sync version across ZigbeeLens packages.
# Usage: ./scripts/bump-version.sh 0.1.0
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <version>" >&2
  exit 1
fi

VERSION="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Bumping to ${VERSION}..."

# Root and JS packages
for pkg in package.json apps/ui/package.json apps/core/package.json packages/shared/package.json; do
  if [[ -f "${ROOT}/${pkg}" ]]; then
    sed -i.bak "s/\"version\": \"[^\"]*\"/\"version\": \"${VERSION}\"/" "${ROOT}/${pkg}"
    rm -f "${ROOT}/${pkg}.bak"
    echo "  ${pkg}"
  fi
done

# Python pyproject
sed -i.bak "s/^version = \"[^\"]*\"/version = \"${VERSION}\"/" "${ROOT}/apps/core/pyproject.toml"
rm -f "${ROOT}/apps/core/pyproject.toml.bak"
echo "  apps/core/pyproject.toml"

# Python __init__
sed -i.bak "s/^__version__ = \"[^\"]*\"/__version__ = \"${VERSION}\"/" \
  "${ROOT}/apps/core/src/zigbeelens/__init__.py"
rm -f "${ROOT}/apps/core/src/zigbeelens/__init__.py.bak"
echo "  apps/core/src/zigbeelens/__init__.py"

# HA add-on
sed -i.bak "s/^version: .*/version: ${VERSION}/" "${ROOT}/apps/addon/zigbeelens/config.yaml"
rm -f "${ROOT}/apps/addon/zigbeelens/config.yaml.bak"
echo "  apps/addon/zigbeelens/config.yaml"

# HACS manifest
sed -i.bak "s/\"version\": \"[^\"]*\"/\"version\": \"${VERSION}\"/" \
  "${ROOT}/apps/ha_integration/custom_components/zigbeelens/manifest.json"
rm -f "${ROOT}/apps/ha_integration/custom_components/zigbeelens/manifest.json.bak"
echo "  apps/ha_integration/.../manifest.json"

echo "Done. Update CHANGELOG.md and commit."
