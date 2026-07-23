#!/usr/bin/env bash
# Validate documentation links, examples, and high-risk public contracts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -n "${CORE_PYTHON:-}" ]]; then
  PYTHON="${CORE_PYTHON}"
elif [[ -x "${ROOT}/apps/core/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/apps/core/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "validate-docs.sh: no Python interpreter found (set CORE_PYTHON or install Core dev dependencies)" >&2
  exit 1
fi

export PYTHONPATH="${ROOT}/apps/core/src${PYTHONPATH:+:${PYTHONPATH}}"
"${PYTHON}" "${ROOT}/scripts/validate-docs.py"
