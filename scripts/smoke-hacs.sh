#!/usr/bin/env bash
# Smoke test: package HACS install repository layout.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== smoke-hacs ==="
bash "${ROOT}/scripts/package-hacs-repo.sh"

STAGE="${ROOT}/dist/zigbeelens-hacs"
test -f "${STAGE}/hacs.json"
test -f "${STAGE}/custom_components/zigbeelens/manifest.json"
test -f "${STAGE}/custom_components/zigbeelens/__init__.py"

echo "OK: smoke-hacs passed — staged at dist/zigbeelens-hacs/"
