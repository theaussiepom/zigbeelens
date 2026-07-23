#!/usr/bin/env bash
# Fail when release artifact versions drift apart.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

read_version() {
  local file="$1"
  local pattern="$2"
  grep -E "$pattern" "$file" | head -1 | sed -E 's/.*"([^"]+)".*/\1/' | sed -E 's/.*version = "([^"]+)".*/\1/' | sed -E 's/^version: "?([^"]+)"?.*/\1/'
}

CORE_PYPROJECT="$(
  grep -E '^version = ' "${ROOT}/apps/core/pyproject.toml" | sed -E 's/version = "([^"]+)"/\1/'
)"
CORE_INIT="$(
  grep -E '^__version__ = ' "${ROOT}/apps/core/src/zigbeelens/__init__.py" | sed -E 's/__version__ = "([^"]+)"/\1/'
)"
UI_PKG="$(
  grep -E '"version"' "${ROOT}/apps/ui/package.json" | head -1 | sed -E 's/.*"version": "([^"]+)".*/\1/'
)"
CORE_PKG="$(
  grep -E '"version"' "${ROOT}/apps/core/package.json" | head -1 | sed -E 's/.*"version": "([^"]+)".*/\1/'
)"
SHARED_PKG="$(
  grep -E '"version"' "${ROOT}/packages/shared/package.json" | head -1 | sed -E 's/.*"version": "([^"]+)".*/\1/'
)"
ROOT_PKG="$(
  grep -E '"version"' "${ROOT}/package.json" | head -1 | sed -E 's/.*"version": "([^"]+)".*/\1/'
)"
HACS_MANIFEST="$(
  grep -E '"version"' "${ROOT}/apps/ha_integration/custom_components/zigbeelens/manifest.json" | sed -E 's/.*"version": "([^"]+)".*/\1/'
)"
ADDON_CONFIG="$(
  grep -E '^version:' "${ROOT}/apps/addon/zigbeelens/config.yaml" | sed -E 's/version: "?([^"]+)"?.*/\1/'
)"
DOCKERFILE="$(
  grep -E '^ARG VERSION=' "${ROOT}/deploy/docker/Dockerfile" | head -1 | sed -E 's/^ARG VERSION=//'
)"

EXPECTED="${CORE_PYPROJECT}"
MISMATCH=0

check() {
  local label="$1"
  local value="$2"
  if [[ "$value" != "$EXPECTED" ]]; then
    echo "version mismatch: ${label}=${value} (expected ${EXPECTED})" >&2
    MISMATCH=1
  fi
}

check "apps/core/pyproject.toml" "$CORE_PYPROJECT"
check "apps/core/__init__" "$CORE_INIT"
check "apps/core/package.json" "$CORE_PKG"
check "apps/ui/package.json" "$UI_PKG"
check "packages/shared/package.json" "$SHARED_PKG"
check "package.json" "$ROOT_PKG"
check "HACS manifest" "$HACS_MANIFEST"
check "add-on config.yaml" "$ADDON_CONFIG"
check "deploy/docker/Dockerfile" "$DOCKERFILE"

if [[ "$MISMATCH" -ne 0 ]]; then
  exit 1
fi

echo "All release versions aligned at ${EXPECTED}"
