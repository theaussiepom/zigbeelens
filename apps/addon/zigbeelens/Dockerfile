# Build from repository root:
#   docker build -f apps/addon/zigbeelens/Dockerfile -t zigbeelens-addon .
#
# Home Assistant Supervisor uses the add-on directory as build context. Run
# scripts/prepare-addon.sh before publishing to a Supervisor-compatible repo,
# or use scripts/build-addon.sh for local image builds from the monorepo root.

FROM node:22-bookworm AS ui-build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-workspace.yaml ./
COPY packages/shared/package.json packages/shared/
COPY apps/ui/package.json apps/ui/
RUN pnpm install --filter @zigbeelens/ui...
COPY packages/shared packages/shared
COPY apps/ui apps/ui
RUN pnpm --filter @zigbeelens/shared build && pnpm --filter @zigbeelens/ui build

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY apps/core/pyproject.toml apps/core/
COPY apps/core/src apps/core/src
RUN pip install --no-cache-dir -e apps/core
COPY --from=ui-build /app/apps/ui/dist /app/static
COPY apps/addon/zigbeelens/run.sh /run.sh
RUN chmod +x /run.sh
ENV PYTHONPATH=/app/apps/core/src
ENV ZIGBEELENS_STATIC_DIR=/app/static
EXPOSE 8377
ENTRYPOINT ["/run.sh"]
