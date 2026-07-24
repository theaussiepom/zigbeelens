#!/usr/bin/env bash
# Run all automated pre-release checks from RELEASE_CHECKLIST.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

export PYTHONPATH="${ROOT}/apps/core/src"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
RELEASE_VERSION="$(
  sed -nE 's/.*"version": "([^"]+)".*/\1/p' "${ROOT}/package.json" | head -1
)"

if ! UV_COMMAND="$(command -v uv 2>/dev/null)" || [[ -z "${UV_COMMAND}" ]]; then
  echo "run-release-checks.sh: uv is required (release workflows provision uv 0.11.16)" >&2
  exit 1
fi

RELEASE_STATE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/zigbeelens-release-python.XXXXXX")"
cleanup() {
  rm -rf "${RELEASE_STATE_DIR}"
}
trap cleanup EXIT

CORE_ENVIRONMENT="${RELEASE_STATE_DIR}/core-environment"
"${UV_COMMAND}" venv \
  --no-project \
  --no-config \
  "${CORE_ENVIRONMENT}"
"${UV_COMMAND}" pip install \
  --no-config \
  --python "${CORE_ENVIRONMENT}/bin/python" \
  --editable "${ROOT}/apps/core[dev]"
export PATH="${CORE_ENVIRONMENT}/bin:${PATH}"
export CORE_PYTHON="${CORE_ENVIRONMENT}/bin/python"
export ZIGBEELENS_CORE_PYTHON="${CORE_PYTHON}"
CORE_RUFF="${CORE_ENVIRONMENT}/bin/ruff"

echo "==> Version alignment"
bash scripts/check-version-alignment.sh

echo "==> Cross-surface contracts and documentation"
bash scripts/validate-contracts.sh

echo "==> Backend lint"
(cd apps/core && "${CORE_RUFF}" check src tests)

echo "==> Backend tests"
(cd apps/core && "${CORE_PYTHON}" -m pytest -q)

echo "==> Performance baselines"
(cd apps/core && "${CORE_PYTHON}" -m pytest -q tests/performance)

echo "==> SQLite 3.34.1 runtime smoke"
bash scripts/smoke-sqlite-3.34.1.sh

echo "==> Safety guardrails"
bash scripts/validate-safety-guardrails.sh

echo "==> UI shared types"
pnpm --filter @zigbeelens/shared build

echo "==> UI shared types typecheck"
pnpm --filter @zigbeelens/shared typecheck

echo "==> UI lint + typecheck + tests + build"
pnpm --filter @zigbeelens/ui lint
pnpm --filter @zigbeelens/ui typecheck
pnpm --filter @zigbeelens/ui test
pnpm --filter @zigbeelens/ui build

echo "==> HA integration"
bash scripts/validate-ha-integration.sh --skip-matrix
bash scripts/test-ha-integration-matrix.sh
echo "==> Live Home Assistant enrichment convergence"
bash scripts/test-enrichment-live-e2e.sh
bash scripts/package-hacs-repo.sh
bash dist/zigbeelens-hacs/scripts/validate-hacs-repo.sh

echo "==> Add-on validation + packaging"
bash scripts/validate-addon.sh
bash scripts/package-addon-repo.sh
bash dist/zigbeelens-addons/scripts/validate-addon-repo.sh

echo "==> Compose validation"
ZIGBEELENS_REQUIRE_DOCKER_COMPOSE=1 bash scripts/validate-compose.sh

echo "==> Core smoke"
bash scripts/smoke-core.sh

echo ""
echo "All automated release checks passed."
echo "Complete manual gates in RELEASE_CHECKLIST.md before tagging v${RELEASE_VERSION}."
