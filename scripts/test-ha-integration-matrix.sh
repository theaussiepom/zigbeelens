#!/usr/bin/env bash
# Run the same integration suite against the exact reviewed Home Assistant lanes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -d "${ROOT}/apps/ha_integration" ]]; then
  HA_DIR="${ROOT}/apps/ha_integration"
elif [[ -d "${ROOT}/custom_components/zigbeelens" ]]; then
  # Generated HACS repository layout.
  HA_DIR="${ROOT}"
else
  echo "FAIL: unable to locate the Home Assistant integration test root" >&2
  exit 1
fi

MATRIX="${HA_DIR}/ha-test-matrix.json"
LANE="${1:-all}"

if [[ "${LANE}" != "all" && "${LANE}" != "minimum" && "${LANE}" != "current" ]]; then
  echo "Usage: $0 [all|minimum|current]" >&2
  exit 2
fi

MATRIX_READER="${ZIGBEELENS_HA_MATRIX_READER:-python3}"
if ! command -v "${MATRIX_READER}" >/dev/null 2>&1; then
  echo "FAIL: matrix reader not found: ${MATRIX_READER}" >&2
  exit 1
fi

HA_MATRIX_TMP="$(mktemp -d "${TMPDIR:-/tmp}/zigbeelens-ha-matrix.XXXXXX")"
cleanup() {
  rm -rf "${HA_MATRIX_TMP}"
}
trap cleanup EXIT

read_lane() {
  local lane="$1"
  "${MATRIX_READER}" - "${MATRIX}" "${lane}" <<'PY'
import json
import sys
from pathlib import Path

matrix_path = Path(sys.argv[1])
lane_name = sys.argv[2]
matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
for lane in matrix["lanes"]:
    if lane["name"] == lane_name:
        print(
            "\t".join(
                (
                    lane["homeassistant"],
                    lane["python"],
                    lane["requirements"],
                )
            )
        )
        raise SystemExit(0)
raise SystemExit(f"unknown Home Assistant matrix lane: {lane_name}")
PY
}

run_lane() {
  local lane="$1"
  local lane_data
  local expected_ha
  local expected_python
  local requirements
  local python_command
  local actual_python
  local venv

  lane_data="$(read_lane "${lane}")"
  IFS=$'\t' read -r expected_ha expected_python requirements <<<"${lane_data}"

  if [[ -n "${ZIGBEELENS_HA_TEST_PYTHON:-}" ]]; then
    python_command="${ZIGBEELENS_HA_TEST_PYTHON}"
  else
    python_command="python${expected_python}"
  fi
  if ! command -v "${python_command}" >/dev/null 2>&1; then
    echo "FAIL: ${lane} lane requires Python ${expected_python}; ${python_command} was not found" >&2
    exit 1
  fi

  actual_python="$(
    "${python_command}" -c \
      'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
  )"
  if [[ "${actual_python}" != "${expected_python}" ]]; then
    echo "FAIL: ${lane} lane requires Python ${expected_python}, got ${actual_python}" >&2
    exit 1
  fi

  venv="${HA_MATRIX_TMP}/${lane}"
  echo "==> HA ${expected_ha} on Python ${expected_python} (${lane})"
  "${python_command}" -m venv "${venv}"
  "${venv}/bin/python" -m pip install \
    --disable-pip-version-check \
    -q \
    -r "${HA_DIR}/${requirements}"

  "${venv}/bin/python" - "${expected_ha}" <<'PY'
from importlib.metadata import version
import sys

expected = sys.argv[1]
actual = version("homeassistant")
if actual != expected:
    raise SystemExit(
        f"Home Assistant version mismatch: installed {actual}, expected {expected}"
    )
print(f"Exact Home Assistant version confirmed: {actual}")
PY

  "${venv}/bin/python" -m pytest -q "${HA_DIR}"
}

if [[ "${LANE}" == "all" ]]; then
  if [[ -n "${ZIGBEELENS_HA_TEST_PYTHON:-}" ]]; then
    echo "FAIL: ZIGBEELENS_HA_TEST_PYTHON may only be used with one exact lane" >&2
    exit 1
  fi
  run_lane minimum
  run_lane current
else
  run_lane "${LANE}"
fi
