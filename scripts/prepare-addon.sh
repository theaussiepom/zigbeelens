#!/usr/bin/env bash
# Stage a Supervisor-compatible add-on build directory (addon dir as context).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="${ROOT}/apps/addon/zigbeelens/.build"
rm -rf "${STAGE}"
mkdir -p "${STAGE}"

rsync -a \
  "${ROOT}/apps/addon/zigbeelens/" \
  --exclude .build \
  "${STAGE}/"

mkdir -p "${STAGE}/apps/core/src" "${STAGE}/apps/ui" "${STAGE}/packages/shared"
rsync -a "${ROOT}/apps/core/pyproject.toml" "${ROOT}/apps/core/README.md" "${STAGE}/apps/core/"
rsync -a "${ROOT}/apps/core/src/" "${STAGE}/apps/core/src/"
rsync -a "${ROOT}/apps/ui/package.json" "${STAGE}/apps/ui/"
rsync -a "${ROOT}/apps/ui/" "${STAGE}/apps/ui/" --exclude node_modules --exclude dist
rsync -a "${ROOT}/packages/shared/" "${STAGE}/packages/shared/" --exclude node_modules --exclude dist
cp "${ROOT}/package.json" "${ROOT}/pnpm-workspace.yaml" "${ROOT}/pnpm-lock.yaml" "${ROOT}/.npmrc" "${STAGE}/"

cat > "${STAGE}/Dockerfile" <<'EOF'
FROM node:22-bookworm AS ui-build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml .npmrc ./
COPY packages/shared/package.json packages/shared/
COPY apps/ui/package.json apps/ui/
RUN pnpm install --filter @zigbeelens/ui... --frozen-lockfile
COPY packages/shared packages/shared
COPY apps/ui apps/ui
RUN pnpm --filter @zigbeelens/shared build && pnpm --filter @zigbeelens/ui build

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY apps/core/pyproject.toml apps/core/README.md apps/core/
COPY apps/core/src apps/core/src
RUN pip install --no-cache-dir -e apps/core
COPY --from=ui-build /app/apps/ui/dist /app/static
COPY run.sh /run.sh
RUN chmod +x /run.sh
ENV PYTHONPATH=/app/apps/core/src
ENV ZIGBEELENS_STATIC_DIR=/app/static
EXPOSE 8377
ENTRYPOINT ["/run.sh"]
EOF

echo "Prepared Supervisor build context at ${STAGE}"
echo "Build with: docker build -t zigbeelens-addon:supervisor ${STAGE}"
