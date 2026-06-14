#!/usr/bin/env bash
# Smoke test: validate add-on packaging files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== smoke-addon ==="
bash "${ROOT}/scripts/validate-addon.sh"

if command -v docker >/dev/null 2>&1; then
  echo "Docker available — add-on image build can be run with ./scripts/build-addon.sh"
else
  echo "SKIP: docker not available for image build"
fi

echo "OK: smoke-addon passed"
