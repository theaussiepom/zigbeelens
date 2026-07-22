#!/usr/bin/env bash
# Fast contract lane: oracle freshness → Core contracts → UI contracts.
# Does not replace full Core/UI/HACS validation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HASH_SEED_A="${PYTHONHASHSEED_A:-1}"
HASH_SEED_B="${PYTHONHASHSEED_B:-42}"

echo "==> Oracle fixture freshness (hash seed ${HASH_SEED_A})"
PYTHONHASHSEED="${HASH_SEED_A}" uv run --directory apps/core python \
  scripts/generate_oracle_mock_fixtures.py --check

echo "==> Oracle fixture freshness (hash seed ${HASH_SEED_B})"
PYTHONHASHSEED="${HASH_SEED_B}" uv run --directory apps/core python \
  scripts/generate_oracle_mock_fixtures.py --check

echo "==> Core contract suite"
uv run --directory apps/core pytest -q tests/contracts

echo "==> UI contract suite"
pnpm --filter @zigbeelens/ui test:contracts

echo "Contract validation OK"
