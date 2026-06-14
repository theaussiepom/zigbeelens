# Release checklist — v0.1.0

Use this checklist before tagging a release. See [docs/release.md](docs/release.md) for the full workflow.

## Tests and validation

- [ ] Backend tests pass (`pytest apps/core/tests -q`)
- [ ] UI tests pass (`pnpm --filter @zigbeelens/ui test`)
- [ ] UI typecheck passes (`pnpm --filter @zigbeelens/ui typecheck`)
- [ ] UI production build passes (`pnpm --filter @zigbeelens/ui build`)
- [ ] HA integration validation passes (`./scripts/validate-ha-integration.sh`)
- [ ] Add-on validation passes (`./scripts/validate-addon.sh`)
- [ ] Compose validation passes (`./scripts/validate-compose.sh`)
- [ ] HACS package builds (`./scripts/package-hacs.sh`)

## Smoke tests

- [ ] Core smoke passes (`./scripts/smoke-core.sh`)
- [ ] Docker smoke passes (`./scripts/smoke-docker.sh`) — if Docker available
- [ ] HACS smoke passes (`./scripts/smoke-hacs.sh`)

## Runtime verification

- [ ] Core starts in mock mode
- [ ] Core starts in live empty mode (valid unknown payloads)
- [ ] HAOS add-on starts (manual or staging)
- [ ] Docker Compose starts
- [ ] Reports generate and redact correctly
- [ ] MQTT Discovery **disabled** by default
- [ ] Topology **disabled** by default
- [ ] No unsafe MQTT topics published

## Safety

- [ ] Safety guardrail tests pass (`test_safety_guardrails.py`)
- [ ] Collector remains subscribe-only
- [ ] UI has no repair/reset/permit-join controls

## Documentation

- [ ] README updated
- [ ] CHANGELOG updated
- [ ] Version numbers aligned (see `./scripts/bump-version.sh`)
- [ ] docs/release.md reflects current process

## Packaging and publish

- [ ] Docker image builds (`./scripts/build-docker.sh`)
- [ ] Add-on image builds (`./scripts/build-addon.sh`)
- [ ] Git tag `v0.1.0` created
- [ ] Docker image pushed to GHCR (on tag)
- [ ] GitHub release notes published
- [ ] Add-on repository metadata updated

## Post-release spot checks

- [ ] Fresh Docker install from docs quick start
- [ ] HACS install from packaged artifact
- [ ] Generate and download a `public_safe` report
- [ ] Confirm SSE/polling works behind reverse proxy (if documented)
