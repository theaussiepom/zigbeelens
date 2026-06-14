#!/usr/bin/env bash
# Smoke test: package HACS integration and verify layout.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== smoke-hacs ==="
bash "${ROOT}/scripts/package-hacs.sh"

STAGE="${ROOT}/dist/hacs/zigbeelens"
test -f "${STAGE}/hacs.json"
test -f "${STAGE}/custom_components/zigbeelens/manifest.json"
test -f "${STAGE}/custom_components/zigbeelens/__init__.py"

echo "OK: smoke-hacs passed — staged at dist/hacs/zigbeelens/"
