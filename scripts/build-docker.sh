#!/usr/bin/env bash
# Build the standalone ZigbeeLens Docker image from the monorepo root.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$ROOT"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

DOCKER_CONTEXT_TMP=""
cleanup() {
  if [[ -n "${DOCKER_CONTEXT_TMP}" && -d "${DOCKER_CONTEXT_TMP}" ]]; then
    rm -rf -- "${DOCKER_CONTEXT_TMP}"
  fi
}
trap cleanup EXIT

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

if [[ ! -f "${ROOT}/.dockerignore" ]]; then
  fail "the canonical build requires the maintained root .dockerignore"
fi

GIT_METADATA_PRESENT=0
GIT_METADATA_PROBE="${ROOT}"
while true; do
  if [[ -e "${GIT_METADATA_PROBE}/.git" ||
    -L "${GIT_METADATA_PROBE}/.git" ]]
  then
    GIT_METADATA_PRESENT=1
    break
  fi
  if [[ "${GIT_METADATA_PROBE}" == "/" ]]; then
    break
  fi
  GIT_METADATA_PROBE="$(dirname "${GIT_METADATA_PROBE}")"
done

DOCKER_CONTEXT="."
DOCKERFILE="deploy/docker/Dockerfile"
REVISION_OVERRIDE_SET=0
REVISION_OVERRIDE=""
if [[ "${ZIGBEELENS_REVISION+x}" == "x" ]]; then
  REVISION_OVERRIDE_SET=1
  REVISION_OVERRIDE="${ZIGBEELENS_REVISION}"
  if [[ ${#REVISION_OVERRIDE} -ne 40 ||
    "${REVISION_OVERRIDE}" == *[!0-9a-f]* ]]
  then
    fail "ZIGBEELENS_REVISION must be a full 40-character lowercase hexadecimal Git SHA"
  fi
fi

if GIT_TOPLEVEL="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  if ! GIT_TOPLEVEL="$(cd "${GIT_TOPLEVEL}" 2>/dev/null && pwd -P)" ||
    [[ "${GIT_TOPLEVEL}" != "${ROOT}" ]]
  then
    fail "build root must be the exact Git checkout root"
  fi
  if ! HEAD_REVISION="$(git rev-parse --verify 'HEAD^{commit}' 2>/dev/null)"; then
    fail "unable to resolve a Git revision from HEAD"
  fi
  if [[ ${#HEAD_REVISION} -ne 40 ||
    "${HEAD_REVISION}" == *[!0-9a-f]* ]]
  then
    fail "resolved HEAD must be a full 40-character lowercase hexadecimal Git SHA"
  fi
  if (( REVISION_OVERRIDE_SET )) &&
    [[ "${REVISION_OVERRIDE}" != "${HEAD_REVISION}" ]]
  then
    fail "ZIGBEELENS_REVISION must match the resolved Git HEAD (${HEAD_REVISION})"
  fi
  if ! WORKTREE_STATUS="$(
    git status \
      --porcelain=v1 \
      --untracked-files=all \
      --ignore-submodules=none 2>/dev/null
  )"; then
    fail "unable to verify that the Git source tree is clean"
  fi
  if [[ -n "${WORKTREE_STATUS}" ]]; then
    echo "${WORKTREE_STATUS}" >&2
    fail "canonical Docker builds require a clean Git source tree"
  fi
  REVISION="${HEAD_REVISION}"
  if ! DOCKER_CONTEXT_TMP="$(
    mktemp -d "${TMPDIR:-/tmp}/zigbeelens-docker-context.XXXXXX"
  )"; then
    fail "unable to create a temporary committed-source Docker context"
  fi
  DOCKER_CONTEXT="${DOCKER_CONTEXT_TMP}/context"
  if ! mkdir -p "${DOCKER_CONTEXT}"; then
    fail "unable to prepare the temporary committed-source Docker context"
  fi
  if ! git archive \
    --format=tar \
    --output="${DOCKER_CONTEXT_TMP}/context.tar" \
    "${REVISION}"
  then
    fail "unable to archive the committed Git source tree"
  fi
  if ! tar -xf "${DOCKER_CONTEXT_TMP}/context.tar" -C "${DOCKER_CONTEXT}"; then
    fail "unable to materialize the committed Git source tree"
  fi
  if [[ ! -f "${DOCKER_CONTEXT}/.dockerignore" ]]; then
    fail "committed HEAD does not contain the maintained root .dockerignore"
  fi
  DOCKERFILE="${DOCKER_CONTEXT}/deploy/docker/Dockerfile"
else
  if (( GIT_METADATA_PRESENT )); then
    fail "Git metadata applies to the build root but Git revision resolution failed"
  fi
  if (( ! REVISION_OVERRIDE_SET )); then
    fail "unable to resolve a Git revision; an immutable source export requires ZIGBEELENS_REVISION and ZIGBEELENS_SOURCE_EXPORT=1"
  fi
  if [[ "${ZIGBEELENS_SOURCE_EXPORT-}" != "1" ]]; then
    fail "a source export without Git metadata requires ZIGBEELENS_SOURCE_EXPORT=1"
  fi
  REVISION="${REVISION_OVERRIDE}"
fi
if [[ ${#REVISION} -ne 40 || "${REVISION}" == *[!0-9a-f]* ]]; then
  fail "ZIGBEELENS_REVISION must be a full 40-character lowercase hexadecimal Git SHA"
fi

IMAGE_SOURCE="https://github.com/theaussiepom/zigbeelens"
IMAGE="${ZIGBEELENS_IMAGE:-ghcr.io/theaussiepom/zigbeelens:latest}"

echo "Building ${IMAGE} (version=${VERSION}, revision=${REVISION}, source=${IMAGE_SOURCE}, context=${DOCKER_CONTEXT})"
docker build \
  -f "${DOCKERFILE}" \
  --build-arg VERSION="${VERSION}" \
  --build-arg REVISION="${REVISION}" \
  --build-arg IMAGE_SOURCE="${IMAGE_SOURCE}" \
  -t "${IMAGE}" \
  -t "ghcr.io/theaussiepom/zigbeelens:${VERSION}" \
  "${DOCKER_CONTEXT}"

echo "Built ${IMAGE}"
echo ""
echo "Quick run:"
echo "  mkdir -p config data"
echo "  cp deploy/docker/config.example.yaml config/config.yaml"
echo "  docker run --rm -p 8377:8377 -v \"\$(pwd)/config:/config:ro\" -v \"\$(pwd)/data:/data\" ${IMAGE}"
