#!/usr/bin/env bash
# Build the standalone ZigbeeLens Docker image from the monorepo root.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$ROOT"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

PACKAGE_VERSION="$(
  sed -nE 's/.*"version": "([^"]+)".*/\1/p' "${ROOT}/package.json" | head -1
)"
STRICT_SEMVER='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(\.(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$'
if [[ ! "${PACKAGE_VERSION}" =~ ${STRICT_SEMVER} ]]; then
  fail "package.json version must be strict SemVer"
fi

if [[ "${ZIGBEELENS_VERSION+x}" == "x" ]]; then
  VERSION="${ZIGBEELENS_VERSION}"
else
  VERSION="${PACKAGE_VERSION}"
fi
if [[ ! "${VERSION}" =~ ${STRICT_SEMVER} ]]; then
  fail "ZIGBEELENS_VERSION must be strict SemVer"
fi
if [[ "${VERSION}" != "${PACKAGE_VERSION}" ]]; then
  fail "ZIGBEELENS_VERSION must match package.json (${PACKAGE_VERSION})"
fi

if [[ "${ZIGBEELENS_REVISION+x}" == "x" ]]; then
  REVISION="${ZIGBEELENS_REVISION}"
else
  if ! GIT_TOPLEVEL="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    fail "unable to resolve a Git revision; set ZIGBEELENS_REVISION to the full source SHA"
  fi
  if ! GIT_TOPLEVEL="$(cd "${GIT_TOPLEVEL}" 2>/dev/null && pwd -P)" ||
    [[ "${GIT_TOPLEVEL}" != "${ROOT}" ]]
  then
    fail "build root must be the exact Git checkout root; set ZIGBEELENS_REVISION for a source export"
  fi
  if ! REVISION="$(git rev-parse --verify 'HEAD^{commit}' 2>/dev/null)"; then
    fail "unable to resolve a Git revision; set ZIGBEELENS_REVISION to the full source SHA"
  fi
fi
if [[ ${#REVISION} -ne 40 || "${REVISION}" == *[!0-9a-f]* ]]; then
  fail "ZIGBEELENS_REVISION must be a full 40-character lowercase hexadecimal Git SHA"
fi

IMAGE_SOURCE="https://github.com/theaussiepom/zigbeelens"
IMAGE="${ZIGBEELENS_IMAGE:-ghcr.io/theaussiepom/zigbeelens:latest}"

echo "Building ${IMAGE} (version=${VERSION}, revision=${REVISION}, source=${IMAGE_SOURCE}, context=${ROOT})"
docker build \
  -f deploy/docker/Dockerfile \
  --build-arg VERSION="${VERSION}" \
  --build-arg REVISION="${REVISION}" \
  --build-arg IMAGE_SOURCE="${IMAGE_SOURCE}" \
  -t "${IMAGE}" \
  -t "ghcr.io/theaussiepom/zigbeelens:${VERSION}" \
  .

echo "Built ${IMAGE}"
echo ""
echo "Quick run:"
echo "  mkdir -p config data"
echo "  cp deploy/docker/config.example.yaml config/config.yaml"
echo "  docker run --rm -p 8377:8377 -v \"\$(pwd)/config:/config:ro\" -v \"\$(pwd)/data:/data\" ${IMAGE}"
