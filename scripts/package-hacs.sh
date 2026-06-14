#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/apps/ha_integration"
DIST="${ROOT}/dist/hacs/zigbeelens"

rm -rf "${DIST}"
mkdir -p "${DIST}/custom_components"

cp -R "${SRC}/custom_components/zigbeelens" "${DIST}/custom_components/"
cp "${SRC}/hacs.json" "${DIST}/"
cp "${SRC}/README.md" "${DIST}/"

echo "Packaged HACS release at ${DIST}"
find "${DIST}" -type f | sort
