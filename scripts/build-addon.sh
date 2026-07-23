#!/usr/bin/env bash
# Build the ZigbeeLens Home Assistant add-on image from the monorepo root.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IMAGE="${ZIGBEELENS_ADDON_IMAGE:-zigbeelens-addon:local}"

echo "Building ${IMAGE} (context: ${ROOT})"
docker build -f apps/addon/zigbeelens/Dockerfile -t "${IMAGE}" .

echo "Built ${IMAGE}"
echo "The add-on image enforces Supervisor Ingress identity and is not a direct"
echo "localhost UI. Install it as a local HAOS add-on and open Supervisor Ingress;"
echo "use scripts/dev.sh for direct browser UI development."
