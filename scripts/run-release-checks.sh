#!/usr/bin/env bash
# Run all automated pre-release checks from RELEASE_CHECKLIST.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

export PYTHONPATH="${ROOT}/apps/core/src"

echo "==> Version alignment"
bash scripts/check-version-alignment.sh

echo "==> Backend lint"
ruff check apps/core/src apps/core/tests

echo "==> Backend tests"
pytest apps/core/tests -q

echo "==> Safety guardrails"
pytest apps/core/tests/test_safety_guardrails.py -q

echo "==> UI shared types"
pnpm --filter @zigbeelens/shared build

echo "==> UI lint + typecheck + tests + build"
pnpm --filter @zigbeelens/ui lint
pnpm --filter @zigbeelens/ui typecheck
pnpm --filter @zigbeelens/ui test
pnpm --filter @zigbeelens/ui build

echo "==> HA integration"
bash scripts/validate-ha-integration.sh
bash scripts/package-hacs-repo.sh

echo "==> Add-on validation + packaging"
bash scripts/validate-addon.sh
bash scripts/package-addon-repo.sh

echo "==> Compose validation"
bash scripts/validate-compose.sh

echo "==> Core smoke"
bash scripts/smoke-core.sh

echo ""
echo "All automated release checks passed."
echo "Complete manual gates in RELEASE_CHECKLIST.md before tagging v0.1.0."
