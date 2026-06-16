#!/usr/bin/env bash
# Validate add-on repository layout (run from repo root).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADDON="${ROOT}/zigbeelens"
FAIL=0

fail() { echo "FAIL: $1" >&2; FAIL=1; }
ok() { echo "OK: $1"; }

echo "=== ZigbeeLens add-on repo validation ==="

for f in repository.yaml zigbeelens/config.yaml zigbeelens/README.md zigbeelens/icon.png zigbeelens/logo.png zigbeelens/translations/en.yaml; do
  if [[ -f "${ROOT}/${f}" ]]; then ok "$f"; else fail "missing $f"; fi
done

grep -q 'ingress_port: 8377' "${ADDON}/config.yaml" && ok "ingress_port 8377" || fail "ingress_port must be 8377"

grep -q '^image: ghcr.io/' "${ADDON}/config.yaml" && ok "GHCR image configured" || fail "image must point to ghcr.io"

grep -q 'password: ""' "${ADDON}/config.yaml" && ok "no embedded default secrets" || fail "check default password field"

grep -q 'mqtt_discovery: false' "${ADDON}/config.yaml" && ok "mqtt_discovery disabled by default" || fail "mqtt_discovery should default false"

grep -q 'topology:' "${ADDON}/config.yaml" && grep -q 'enabled: true' "${ADDON}/config.yaml" && grep -q 'startup_scan: true' "${ADDON}/config.yaml" && ok "topology enabled with startup scan by default" || fail "topology should default enabled with startup_scan"

if [[ "${FAIL}" -ne 0 ]]; then exit 1; fi
echo "Add-on repo validation passed."
