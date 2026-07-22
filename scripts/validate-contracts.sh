#!/usr/bin/env bash
# Fast contract lane: Core contracts (owns oracle freshness) → UI contracts.
# Self-contained: does not require uv. CI may use pip-installed Core.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Tests may override the repository root via ZIGBEELENS_CONTRACT_ROOT.
ROOT="${ZIGBEELENS_CONTRACT_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"

resolve_core_python() {
  if [[ -n "${CORE_PYTHON:-}" ]]; then
    printf '%s\n' "${CORE_PYTHON}"
    return 0
  fi
  local venv_python="${ROOT}/apps/core/.venv/bin/python"
  if [[ -x "${venv_python}" ]]; then
    printf '%s\n' "${venv_python}"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  echo "validate-contracts.sh: no Python interpreter found (set CORE_PYTHON, create apps/core/.venv, or install python3)" >&2
  return 1
}

main() {
  if [[ "${1:-}" == "--print-core-python" ]]; then
    resolve_core_python
    return 0
  fi

  local core_python
  core_python="$(resolve_core_python)"
  export PYTHONPATH="${ROOT}/apps/core/src${PYTHONPATH:+:${PYTHONPATH}}"

  echo "==> Core contract suite (oracle freshness owner; Python=${core_python})"
  (
    cd "${ROOT}/apps/core"
    "${core_python}" -m pytest -q tests/contracts
  )

  echo "==> UI contract suite"
  (
    cd "${ROOT}"
    pnpm --filter @zigbeelens/ui test:contracts
  )

  echo "Contract validation OK"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
