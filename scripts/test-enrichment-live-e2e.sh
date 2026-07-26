#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
uv_command="${ZIGBEELENS_UV:-$(command -v uv || true)}"
hacs_stage="$repo_root/dist/zigbeelens-hacs"

state_dir="$(mktemp -d "${TMPDIR:-/tmp}/zigbeelens-enrichment-live.XXXXXX")"
core_url_file="$state_dir/core-url"
ha_url_file="$state_dir/ha-url"
ha_version_file="$state_dir/ha-version"
ha_provenance_file="$state_dir/ha-provenance"
ha_config_dir="$state_dir/home-assistant"
ha_components_dir="$ha_config_dir/custom_components"
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

echo "==> Fresh staged HACS integration"
bash "$repo_root/scripts/package-hacs-repo.sh"
bash "$hacs_stage/scripts/validate-hacs-repo.sh"
source_commit="$(git -C "$repo_root" rev-parse --verify 'HEAD^{commit}')"
staged_source_commit="$(tr -d '[:space:]' < "$hacs_stage/SOURCE_COMMIT")"
if [[ "$staged_source_commit" != "$source_commit" ]]; then
  echo "Staged HACS SOURCE_COMMIT does not equal HEAD" >&2
  exit 1
fi
mkdir -p "$ha_config_dir"
cp -R "$hacs_stage/custom_components" "$ha_config_dir/"
cp "$hacs_stage/SOURCE_COMMIT" "$ha_config_dir/SOURCE_COMMIT"
if ! diff -qr \
  "$hacs_stage/custom_components" \
  "$ha_components_dir" >/dev/null
then
  echo "Disposable Home Assistant integration differs from the HACS stage" >&2
  exit 1
fi

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

PYTHONASYNCIODEBUG=1 \
"${ha_command[@]}" "$repo_root/tests/e2e/enrichment_live/ha_control_server.py" \
  --core-url "$core_url" \
  --config-dir "$ha_config_dir" \
  --components-dir "$ha_components_dir" \
  --source-commit "$source_commit" \
  --url-file "$ha_url_file" \
  --version-file "$ha_version_file" \
  --provenance-file "$ha_provenance_file" \
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
ha_provenance="$(tr -d '\r\n' < "$ha_provenance_file")"
if [[ "$ha_provenance" != "$source_commit|0.1.14" ]]; then
  cat "$state_dir/home-assistant.log" >&2
  echo "Disposable Home Assistant integration provenance is invalid" >&2
  exit 1
fi
echo "Home Assistant E2E lane: Python 3.12 / Home Assistant 2025.1.0"
echo "Home Assistant E2E staged source: $source_commit / ZigbeeLens 0.1.14"

if ! (
  cd "$repo_root/apps/ui"
  ZIGBEELENS_E2E_CORE_URL="$core_url" \
    ZIGBEELENS_E2E_HA_CONTROL_URL="$ha_url" \
    VITE_API_BASE="$core_url/" \
    pnpm exec vitest run \
      --config vitest.e2e.config.ts
); then
  cat "$state_dir/home-assistant.log" >&2
  exit 1
fi

kill "$ha_pid"
if ! wait "$ha_pid"; then
  cat "$state_dir/home-assistant.log" >&2
  echo "Home Assistant E2E harness exited with an error" >&2
  exit 1
fi
ha_pid=""

if grep -Eiq \
  'from a thread other than the event loop|non-thread-safe operation invoked on an event loop|task exception was never retrieved|exception in callback' \
  "$state_dir/home-assistant.log"
then
  cat "$state_dir/home-assistant.log" >&2
  echo "Home Assistant E2E harness logged an event-loop error" >&2
  exit 1
fi
