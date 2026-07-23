#!/usr/bin/env bash
# Build the standalone ZigbeeLens Docker image from the monorepo root.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PACKAGE_VERSION="$(
  sed -nE 's/.*"version": "([^"]+)".*/\1/p' "${ROOT}/package.json" | head -1
)"
VERSION="${ZIGBEELENS_VERSION:-${PACKAGE_VERSION}}"
IMAGE="${ZIGBEELENS_IMAGE:-ghcr.io/theaussiepom/zigbeelens:latest}"

echo "Building ${IMAGE} (version=${VERSION}, context=${ROOT})"
docker build \
  -f deploy/docker/Dockerfile \
  --build-arg VERSION="${VERSION}" \
  -t "${IMAGE}" \
  -t "ghcr.io/theaussiepom/zigbeelens:${VERSION}" \
  .

echo "Built ${IMAGE}"
echo ""
echo "Quick run:"
echo "  mkdir -p config data"
echo "  cp deploy/docker/config.example.yaml config/config.yaml"
echo "  docker run --rm -p 8377:8377 -v \"\$(pwd)/config:/config:ro\" -v \"\$(pwd)/data:/data\" ${IMAGE}"
