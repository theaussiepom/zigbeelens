#!/usr/bin/env bash
# Smoke test: start Core in mock mode and verify key endpoints.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${SMOKE_PORT:-8377}"
BASE="http://127.0.0.1:${PORT}"
PID=""

cleanup() {
  if [[ -n "${PID}" ]] && kill -0 "${PID}" 2>/dev/null; then
    kill "${PID}" 2>/dev/null || true
    wait "${PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

cd "${ROOT}"

if [[ ! -d apps/core/.venv ]]; then
  python3 -m venv apps/core/.venv
fi
# shellcheck disable=SC1091
source apps/core/.venv/bin/activate
pip install -q -e "apps/core[dev]"

export ZIGBEELENS_CONFIG="${ROOT}/config/config.yaml"
export PYTHONPATH="${ROOT}/apps/core/src"

echo "=== smoke-core: starting Core on port ${PORT} ==="
python -m uvicorn zigbeelens.main:app --host 127.0.0.1 --port "${PORT}" &
PID=$!

for i in $(seq 1 30); do
  if curl -sf "${BASE}/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

echo "Checking /healthz..."
curl -sf "${BASE}/healthz" | grep -q '"status"' || { echo "FAIL: /healthz"; exit 1; }

echo "Checking /api/dashboard..."
curl -sf "${BASE}/api/dashboard" | grep -q '"overall_severity"' || { echo "FAIL: /api/dashboard"; exit 1; }

echo "Checking /api/version..."
curl -sf "${BASE}/api/version" | grep -q '"version"' || { echo "FAIL: /api/version"; exit 1; }

echo "Checking / (static UI or fallback)..."
code=$(curl -sf -o /dev/null -w '%{http_code}' "${BASE}/")
[[ "${code}" == "200" ]] || { echo "FAIL: / returned ${code}"; exit 1; }

echo "OK: smoke-core passed"
