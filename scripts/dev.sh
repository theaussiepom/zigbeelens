#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export ZIGBEELENS_CONFIG="${ZIGBEELENS_CONFIG:-$ROOT/config/config.yaml}"

if ! command -v pnpm >/dev/null 2>&1; then
  corepack enable
  corepack prepare pnpm@9.15.0 --activate
fi

pnpm install
pnpm --filter @zigbeelens/shared build

if [[ ! -d apps/core/.venv ]]; then
  python3 -m venv apps/core/.venv
fi
# shellcheck disable=SC1091
source apps/core/.venv/bin/activate
pip install -q -e "apps/core[dev]"

echo "Config: $ZIGBEELENS_CONFIG"
echo "Starting ZigbeeLens Core on :8377 and UI on :5173"
PYTHONPATH=apps/core/src uvicorn zigbeelens.main:app --host 0.0.0.0 --port 8377 --reload &
CORE_PID=$!
pnpm --filter @zigbeelens/ui dev &
UI_PID=$!
trap 'kill $CORE_PID $UI_PID 2>/dev/null || true' EXIT
wait
