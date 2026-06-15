# Release checklist — v0.1.0

Use this checklist before tagging a release. See [docs/release.md](docs/release.md) for the full workflow.

## Automated tests and validation

- [ ] Backend tests pass (`pytest apps/core/tests -q`)
- [ ] UI tests pass (`pnpm --filter @zigbeelens/ui test`)
- [ ] UI typecheck passes (`pnpm --filter @zigbeelens/ui typecheck`)
- [ ] UI production build passes (`pnpm --filter @zigbeelens/ui build`)
- [ ] HA integration validation passes (`./scripts/validate-ha-integration.sh`)
- [ ] Add-on validation passes (`./scripts/validate-addon.sh`)
- [ ] Compose validation passes (`./scripts/validate-compose.sh`)
- [ ] HACS package builds (`./scripts/package-hacs-repo.sh`)
- [ ] Add-on package builds (`./scripts/package-addon-repo.sh`)
- [ ] Core smoke passes (`./scripts/smoke-core.sh`)
- [ ] Version alignment check passes (`./scripts/check-version-alignment.sh`)
- [ ] Storage retention enforcement is **not** included in v0.1.0 — monitor database size on long-running installs

## Manual gates — real-world (Beast / production-like)

- [ ] Real GHCR edge container tested on Beast (`ghcr.io/theaussiepom/zigbeelens:edge`)
- [ ] Real MQTT broker tested with dedicated `zigbeelens` user (subscribe-only)
- [ ] Both real networks visible: `home`, `home2`
- [ ] Real report generation tested
- [ ] `public_safe` redaction tested with real data (password / network_key scrubbed)
- [ ] Docker logs secret-free

## Manual gates — HACS integration

- [ ] HACS integration installed from custom repo (`theaussiepom/zigbeelens-hacs`)
- [ ] Config flow accepts Core URL reachable from Home Assistant
- [ ] Native companion panel loads (cards, not raw JSON)
- [ ] **Open Full Dashboard** button opens Core in a new tab (e.g. `http://192.168.100.5:8377`)
- [ ] **Try Embedded View** button appears
- [ ] Native companion panel loads with HTTP Core URL
- [ ] **Open Full Dashboard** button opens Core in a new tab (e.g. `http://192.168.100.5:8377`)
- [ ] Configure flow can change Core URL to HTTPS without delete/re-add
- [ ] If HA is HTTPS and Core is HTTP, Try Embedded View shows friendly blocked explanation
- [ ] If using HTTPS Core URL, Try Embedded View renders full dashboard inside HA
- [ ] Copy Core URL works
- [ ] HACS entities appear (overall health, active incident, device counts, per-network)
- [ ] Stop Core → panel shows calm disconnected state + Core unreachable repair
- [ ] Start Core → panel recovers and repair clears
- [ ] HACS diagnostics download is redacted (no secrets)

## Manual gates — mobile polish

- [ ] Core React dashboard pass at ~360–430px width (Overview, Incidents, Devices, Reports, Settings)
- [ ] No horizontal page overflow on phone-sized viewport
- [ ] HACS native companion panel pass on phone/tablet HA web/app
- [ ] Open Full Dashboard button obvious on mobile

## Manual gates — add-on readiness (structural; HAOS install may be deferred)

- [ ] Add-on repo validates (`./scripts/validate-addon.sh` + packaged repo check)
- [ ] No privileged mode, no host network, no Docker socket
- [ ] Ingress enabled; safe defaults (`mqtt_discovery: false`, topology off)
- [ ] Add-on README accurate (Ingress = embedded dashboard path; HACS optional)
- [ ] HAOS manual install smoke test (optional before v0.1.0 tag; required before add-on publish)

## Runtime verification

- [ ] Core starts in mock mode
- [ ] Core starts in live empty mode (valid unknown payloads)
- [ ] Docker Compose starts
- [ ] Reports generate and redact correctly
- [ ] MQTT Discovery **disabled** by default
- [ ] Topology **disabled** by default
- [ ] No unsafe MQTT topics published with default config
- [ ] SSE `/api/events/stream` works (not shadowed by static SPA catch-all)

## Safety

- [ ] Safety guardrail tests pass (`test_safety_guardrails.py`)
- [ ] Collector remains subscribe-only (default path)
- [ ] UI has no repair/reset/permit-join controls
- [ ] HACS panel summary and diagnostics exclude secrets

## Documentation

- [ ] README updated
- [ ] CHANGELOG updated
- [ ] Version numbers aligned (see `./scripts/bump-version.sh`)
- [ ] Docs describe Docker + HACS native panel + add-on Ingress relationship
- [ ] No docs promise iframe as normal HACS experience
- [ ] No docs imply reverse proxy required for HACS sidebar value
- [ ] README screenshot placeholders replaced or consciously accepted

## Packaging and publish

- [ ] Docker image builds (`./scripts/build-docker.sh`)
- [ ] Git tag `v0.1.0` created **only after manual gates above pass**
- [ ] Docker image pushed to GHCR (`ghcr.io/theaussiepom/zigbeelens:0.1.0`)
- [ ] HACS repo version coherent with integration manifest
- [ ] HACS repo pushed (`theaussiepom/zigbeelens-hacs`)
- [ ] GitHub release notes published
- [ ] Add-on repository metadata updated (when add-on is published)

## Post-release spot checks

- [ ] Fresh Docker install from docs quick start
- [ ] HACS install from published repo
- [ ] Generate and download a `public_safe` report
- [ ] Confirm SSE works when Core is behind reverse proxy (optional advanced Docker path — see [docs/hacs-embedded-view.md](docs/hacs-embedded-view.md) for Caddy example)
