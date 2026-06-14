# Standalone ZigbeeLens production image (Core + bundled UI).
# Build from repository root:
#   docker build -f deploy/docker/Dockerfile -t ghcr.io/zigbeelens/zigbeelens:latest .
#
# Home Assistant add-on uses apps/addon/zigbeelens/Dockerfile (options.json → config).

ARG VERSION=0.1.0
ARG IMAGE_SOURCE=https://github.com/theaussiepom/zigbeelens

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
ARG VERSION
ARG IMAGE_SOURCE
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r zigbeelens -g 1000 \
    && useradd -r -u 1000 -g zigbeelens -d /app -s /usr/sbin/nologin zigbeelens \
    && mkdir -p /data /config /app/static

COPY apps/core/pyproject.toml apps/core/README.md /tmp/core/
COPY apps/core/src /tmp/core/src
RUN pip install --no-cache-dir /tmp/core && rm -rf /tmp/core

COPY --from=ui-build /app/apps/ui/dist /app/static
COPY deploy/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && chown -R zigbeelens:zigbeelens /app /data /config

ENV ZIGBEELENS_STATIC_DIR=/app/static \
    ZIGBEELENS_CONFIG=/config/config.yaml \
    ZIGBEELENS_LOG_LEVEL=INFO \
    ZIGBEELENS_PORT=8377 \
    PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.title="ZigbeeLens" \
      org.opencontainers.image.description="Read-only observability console for Zigbee2MQTT networks" \
      org.opencontainers.image.source="${IMAGE_SOURCE}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="MIT"

EXPOSE 8377

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8377/api/health', timeout=5)"

USER zigbeelens
VOLUME ["/config", "/data"]
ENTRYPOINT ["/entrypoint.sh"]
