#!/usr/bin/env bash
# Build the ZigbeeLens Home Assistant add-on image from the monorepo root.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IMAGE="${ZIGBEELENS_ADDON_IMAGE:-zigbeelens-addon:local}"

echo "Building ${IMAGE} (context: ${ROOT})"
docker build -f apps/addon/zigbeelens/Dockerfile -t "${IMAGE}" .

echo "Built ${IMAGE}"
echo "Run locally:"
echo "  docker run --rm -p 8377:8377 -v \$(pwd)/data/ha-addon:/data ${IMAGE}"
