#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
uv_command="${ZIGBEELENS_UV:-$(command -v uv || true)}"

state_dir="$(mktemp -d "${TMPDIR:-/tmp}/zigbeelens-enrichment-live.XXXXXX")"
core_url_file="$state_dir/core-url"
ha_url_file="$state_dir/ha-url"
ha_version_file="$state_dir/ha-version"
core_pid=""
ha_pid=""

cleanup() {
  if [[ -n "$ha_pid" ]]; then
    kill "$ha_pid" 2>/dev/null || true
    wait "$ha_pid" 2>/dev/null || true
  fi
  if [[ -n "$core_pid" ]]; then
    kill "$core_pid" 2>/dev/null || true
    wait "$core_pid" 2>/dev/null || true
  fi
  rm -rf "$state_dir"
}
trap cleanup EXIT INT TERM

if [[ -n "${ZIGBEELENS_CORE_PYTHON:-}" ]]; then
  if [[ ! -x "$ZIGBEELENS_CORE_PYTHON" ]]; then
    echo "Core test Python is unavailable: $ZIGBEELENS_CORE_PYTHON" >&2
    exit 1
  fi
  core_command=("$ZIGBEELENS_CORE_PYTHON")
else
  if [[ -z "$uv_command" ]]; then
    echo "uv is required for the Core E2E harness" >&2
    exit 1
  fi
  core_command=("$uv_command" run --project "$repo_root/apps/core" python)
fi

if [[ -n "${ZIGBEELENS_HA_PYTHON:-}" ]]; then
  if [[ ! -x "$ZIGBEELENS_HA_PYTHON" ]]; then
    echo "Home Assistant test Python is unavailable: $ZIGBEELENS_HA_PYTHON" >&2
    exit 1
  fi
  ha_command=("$ZIGBEELENS_HA_PYTHON")
else
  if [[ -z "$uv_command" ]]; then
    echo "uv is required for the exact Home Assistant minimum lane" >&2
    exit 1
  fi
  ha_command=(
    "$uv_command" run
    --no-project
    --python 3.12
    --prerelease allow
    --with-requirements "$repo_root/apps/ha_integration/requirements-test-minimum.txt"
    python
  )
fi

"${core_command[@]}" "$repo_root/tests/e2e/enrichment_live/core_server.py" \
  --state-dir "$state_dir/core" \
  --url-file "$core_url_file" \
  >"$state_dir/core.log" 2>&1 &
core_pid=$!

for _attempt in {1..100}; do
  if [[ -s "$core_url_file" ]]; then
    core_url="$(tr -d '\r\n' < "$core_url_file")"
    if curl --fail --silent --show-error "$core_url/healthz" >/dev/null 2>&1; then
      break
    fi
  fi
  if ! kill -0 "$core_pid" 2>/dev/null; then
    cat "$state_dir/core.log" >&2
    exit 1
  fi
  sleep 0.1
done
if [[ -z "${core_url:-}" ]] || ! curl --fail --silent "$core_url/healthz" >/dev/null; then
  cat "$state_dir/core.log" >&2
  echo "Core E2E harness did not become ready" >&2
  exit 1
fi

"${ha_command[@]}" "$repo_root/tests/e2e/enrichment_live/ha_control_server.py" \
  --core-url "$core_url" \
  --config-dir "$state_dir/home-assistant" \
  --url-file "$ha_url_file" \
  --version-file "$ha_version_file" \
  >"$state_dir/home-assistant.log" 2>&1 &
ha_pid=$!

for _attempt in {1..600}; do
  if [[ -s "$ha_url_file" ]]; then
    ha_url="$(tr -d '\r\n' < "$ha_url_file")"
    if curl --fail --silent --show-error "$ha_url/health" >/dev/null 2>&1; then
      break
    fi
  fi
  if ! kill -0 "$ha_pid" 2>/dev/null; then
    cat "$state_dir/home-assistant.log" >&2
    exit 1
  fi
  sleep 0.1
done
if [[ -z "${ha_url:-}" ]] || ! curl --fail --silent "$ha_url/health" >/dev/null; then
  cat "$state_dir/home-assistant.log" >&2
  echo "Home Assistant E2E harness did not become ready" >&2
  exit 1
fi
ha_lane="$(tr -d '\r\n' < "$ha_version_file")"
if [[ "$ha_lane" != "3.12|2025.1.0" ]]; then
  cat "$state_dir/home-assistant.log" >&2
  echo "Expected Python 3.12 with Home Assistant 2025.1.0, got $ha_lane" >&2
  exit 1
fi
echo "Home Assistant E2E lane: Python 3.12 / Home Assistant 2025.1.0"

(
  cd "$repo_root/apps/ui"
  ZIGBEELENS_E2E_CORE_URL="$core_url" \
    ZIGBEELENS_E2E_HA_CONTROL_URL="$ha_url" \
    VITE_API_BASE="$core_url/" \
    pnpm exec vitest run \
      --config vitest.e2e.config.ts
)
