#!/usr/bin/env bash
# Validate Docker/Compose deployment files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCKER="${ROOT}/deploy/docker"
FAIL=0

fail() {
  echo "FAIL: $1" >&2
  FAIL=1
}

ok() {
  echo "OK: $1"
}

echo "=== ZigbeeLens Docker/Compose validation ==="

for f in \
  "${DOCKER}/Dockerfile" \
  "${DOCKER}/entrypoint.sh" \
  "${DOCKER}/config.example.yaml" \
  "${DOCKER}/config.multi-network.example.yaml" \
  "${DOCKER}/docker-compose.example.yaml" \
  "${DOCKER}/docker-compose.mosquitto.example.yaml" \
  "${DOCKER}/docker-compose.traefik.example.yaml" \
  "${DOCKER}/docker-compose.caddy.example.yaml" \
  "${DOCKER}/docker-compose.beast-traefik.example.yaml" \
  "${DOCKER}/Caddyfile.example" \
  "${ROOT}/deploy/traefik/security-headers-zigbeelens.yaml.example" \
  "${DOCKER}/README.md" \
  "${ROOT}/docs/docker.md" \
  "${ROOT}/docs/hacs-embedded-view.md" \
  "${ROOT}/docs/upgrades.md" \
  "${ROOT}/docs/backups.md"
do
  if [[ -f "$f" ]]; then ok "$f"; else fail "missing $f"; fi
done

if [[ -x "${DOCKER}/entrypoint.sh" ]] || grep -q entrypoint "${DOCKER}/Dockerfile"; then
  ok "entrypoint configured"
else
  fail "entrypoint.sh should be executable or referenced in Dockerfile"
fi

if grep -q 'EXPOSE 8377' "${DOCKER}/Dockerfile"; then
  ok "Dockerfile exposes port 8377"
else
  fail "Dockerfile must EXPOSE 8377"
fi

if grep -q 'HEALTHCHECK' "${DOCKER}/Dockerfile"; then
  ok "Dockerfile HEALTHCHECK present"
else
  fail "Dockerfile missing HEALTHCHECK"
fi

if grep -q 'healthz' "${DOCKER}/Dockerfile" && grep -q 'docker_healthcheck' "${DOCKER}/Dockerfile"; then
  ok "healthcheck uses /healthz via docker_healthcheck module"
else
  fail "healthcheck should call /healthz via docker_healthcheck module"
fi

if grep -q 'ZIGBEELENS_CONFIG=/config/config.yaml' "${DOCKER}/Dockerfile"; then
  ok "default config path is /config/config.yaml"
else
  fail "ZIGBEELENS_CONFIG should default to /config/config.yaml"
fi

for compose in \
  "${DOCKER}/docker-compose.example.yaml" \
  "${DOCKER}/docker-compose.mosquitto.example.yaml" \
  "${DOCKER}/docker-compose.traefik.example.yaml" \
  "${DOCKER}/docker-compose.caddy.example.yaml" \
  "${DOCKER}/docker-compose.beast-traefik.example.yaml"
do
  if grep -q 'docker.sock' "$compose" 2>/dev/null; then
    fail "docker.sock mount in $(basename "$compose")"
  fi
  if grep -q 'privileged: true' "$compose" 2>/dev/null; then
    fail "privileged mode in $(basename "$compose")"
  fi
  if grep -q 'network_mode: host' "$compose" 2>/dev/null; then
    fail "host networking in $(basename "$compose")"
  fi
done
ok "compose files avoid docker.sock, privileged, and host networking"

if grep -qiE 'access.control|reverse proxy|authentication|HTTPS is not' "${ROOT}/docs/docker.md"; then
  ok "docker docs mention access control / reverse proxy"
else
  fail "docs/docker.md should mention access control or reverse proxy auth"
fi

if [[ -d "${ROOT}/apps/core/.venv" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT}/apps/core/.venv/bin/activate"
fi
PYTHONPATH="${ROOT}/apps/core/src" python3 -m pytest -q "${ROOT}/apps/core/tests/test_docker_deploy.py" || FAIL=1

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  for compose in \
    "${DOCKER}/docker-compose.example.yaml" \
    "${DOCKER}/docker-compose.mosquitto.example.yaml" \
    "${DOCKER}/docker-compose.traefik.example.yaml" \
    "${DOCKER}/docker-compose.caddy.example.yaml" \
    "${DOCKER}/docker-compose.beast-traefik.example.yaml"
  do
    if [[ "$(basename "$compose")" == "docker-compose.caddy.example.yaml" ]]; then
      cp -f "${DOCKER}/Caddyfile.example" "${DOCKER}/Caddyfile"
      if (cd "${DOCKER}" && docker compose -f docker-compose.caddy.example.yaml config >/dev/null 2>&1); then
        ok "docker compose config: $(basename "$compose")"
      else
        fail "docker compose config failed: $(basename "$compose")"
      fi
      rm -f "${DOCKER}/Caddyfile"
      continue
    fi
    if [[ "$(basename "$compose")" == "docker-compose.beast-traefik.example.yaml" ]]; then
      if (
        cd "${DOCKER}" &&
        DOMAIN=theaussiepom.me TZ=UTC HASS_TABLETS_TRAEFIK='Header(`X-Tablet`, `1`)' \
          docker compose -f docker-compose.beast-traefik.example.yaml config >/dev/null 2>&1
      ); then
        ok "docker compose config: $(basename "$compose")"
      else
        fail "docker compose config failed: $(basename "$compose")"
      fi
      continue
    fi
    if docker compose -f "$compose" config >/dev/null 2>&1; then
      ok "docker compose config: $(basename "$compose")"
    else
      fail "docker compose config failed: $(basename "$compose")"
    fi
  done

  CANONICAL_COMPOSE="${DOCKER}/docker-compose.example.yaml"
  if DEFAULT_RENDER="$(
    env -u ZIGBEELENS_IMAGE \
      docker compose --env-file /dev/null -f "${CANONICAL_COMPOSE}" config 2>/dev/null
  )" \
    && grep -q 'image: ghcr.io/theaussiepom/zigbeelens:latest' <<<"${DEFAULT_RENDER}"; then
    ok "canonical Compose default resolves to latest tagged release"
  else
    fail "canonical Compose default image did not resolve to latest"
  fi
  if EDGE_RENDER="$(
    env ZIGBEELENS_IMAGE=ghcr.io/theaussiepom/zigbeelens:edge \
      docker compose --env-file /dev/null -f "${CANONICAL_COMPOSE}" config 2>/dev/null
  )" && grep -q 'image: ghcr.io/theaussiepom/zigbeelens:edge' <<<"${EDGE_RENDER}"; then
    ok "canonical Compose accepts explicit edge override"
  else
    fail "canonical Compose did not accept ZIGBEELENS_IMAGE=edge override"
  fi
else
  echo "SKIP: docker compose config (docker not available)"
fi

if [[ "${FAIL}" -ne 0 ]]; then
  echo "Docker/Compose validation failed."
  exit 1
fi

echo "Docker/Compose validation passed."
