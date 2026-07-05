#!/usr/bin/env bash
# Validate add-on repository layout (delegates to canonical script).
set -euo pipefail
CANONICAL="$(cd "$(dirname "$0")/../.." && pwd)/scripts/validate-addon-repo.sh"
exec bash "${CANONICAL}"
