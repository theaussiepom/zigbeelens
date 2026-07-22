# Release checklist — v0.1.0

Use this checklist before tagging a release. See [docs/release.md](docs/release.md) for the full workflow.

## Automated tests and validation

Run all automated checks:

```bash
./scripts/run-release-checks.sh
```

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
- [ ] Storage retention policy v2: telemetry / resolved incidents / reports; startup + periodic maintenance
- [ ] `zigbeelens storage check` / `backup` / `maintenance --dry-run` validated on a release candidate DB

## Security acknowledgement

- [ ] I have set the intended `security.mode` (and know what this build actually enforces).
- [ ] I understand the process bind (`server.host`) — loopback vs non-loopback — and that status/Uvicorn share one AppConfig.
- [ ] I have decided whether to configure an API token (`ZIGBEELENS_SECURITY_API_TOKEN` / `_FILE` or legacy `ZIGBEELENS_API_KEY` config alias).
- [ ] If a token is set, I understand protected reads, mutations, SSE, and downloads require `Authorization: Bearer` (not `X-ZigbeeLens-Api-Key`).
- [ ] If I also set `session_secret`, I understand browser sessions use an HttpOnly cookie and cookie mutations need `X-ZigbeeLens-CSRF-Token`.
- [ ] I understand `local` without a token is trusted-open; the bundled UI uses session login when both token and session secret are set; add-on UI uses Home Assistant ingress identity (no token required); HACS may store the optional Core API token for server-side bearer reads (never in panel/iframe URLs).
- [ ] Standalone UI: trusted-open enters directly; existing session reloads; wrong token stays locked; correct token cookie round-trip unlocks; mutations send CSRF; SSE and report download use cookies; expiry/logout return to login; API token is absent from browser storage.
- [ ] I have checked logs/config status for accidental secret leakage.
- [ ] If Core is reachable beyond users/networks I trust, I have intentionally added a trusted proxy/firewall (or accepted the risk).
- [ ] I understand ZigbeeLens is read-only for Zigbee control and does not perform permit join, remove, reset, bind/unbind, OTA, or channel changes.
- [ ] I understand some API routes can modify ZigbeeLens local data, such as reports, topology snapshots, and Home Assistant enrichment metadata.
- [ ] If using an FQDN/HTTPS route, I understand HTTPS is not authentication.
- [ ] If using a tablet/no-auth route, I have intentionally scoped it to trusted/local access or accepted the risk.

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
- [ ] **Open Full Dashboard** opens Core in a new tab (e.g. `http://192.168.100.5:8377`)
- [ ] Native companion summary is the default; Try Embedded View opts into iframe mode when schemes match
- [ ] When HA is HTTPS and Core is HTTP, panel stays on native summary / blocked view (mixed content blocked)
- [ ] Back to Summary returns from embedded or blocked view to the native panel
- [ ] Configure flow can change Core URL without delete/re-add; panel picks up new URL after reload
- [ ] Copy Core URL works
- [ ] HACS entities appear (overall health, active incident, device counts, per-network)
- [ ] Stop Core → panel shows calm disconnected state + Core unreachable repair
- [ ] Start Core → panel recovers and repair clears
- [ ] HACS diagnostics download is redacted (no secrets)
- [ ] Behind TLS reverse proxy: `cors_allowed_origins` includes the browser-visible `https://…` Core origin for sessions; `frame_ancestor_origins` lists HA separately when embedding

## Manual gates — mobile polish

- [ ] Core React dashboard pass at ~360–430px width (Overview, Incidents, Devices, Reports, Settings)
- [ ] No horizontal page overflow on phone-sized viewport
- [ ] HACS native companion panel pass on phone/tablet HA web/app
- [ ] Open Full Dashboard button obvious on mobile

## Manual gates — add-on readiness (structural; HAOS install may be deferred)

- [ ] Add-on repo validates (`./scripts/validate-addon.sh` + packaged repo check)
- [ ] No privileged mode, no host network, no Docker socket
- [ ] Ingress enabled; safe defaults (`mqtt_discovery: false`, topology off)
- [ ] Add-on README accurate (Ingress UI uses HA identity; optional bearer for HACS)
- [ ] Add-on with no API token: ingress UI opens, SSE/download/mutation work; direct protected request fails
- [ ] Add-on with optional token: ingress still works; HACS/direct bearer succeeds
- [ ] Spoofed ingress identity from a non-Supervisor peer fails
- [ ] HAOS manual install smoke test (optional before v0.1.0 tag; required before add-on publish)

## Decision contract / Track 5

- [ ] Capabilities advertise `decision_contract_version: 2` and `legacy_health_lens_payloads: false`
- [ ] Current Dashboard/Devices/Networks/Incidents payloads have no Lens/health presentation fields
- [ ] Saved reports are exact `report_version: 3`; non-v3 rows are not listed or downloaded
- [ ] HACS requires exact contract v2; incompatible Core shows repair (not reauth) and no health fallback
- [ ] MQTT Discovery publishes decision summary entities; superseded Lens configs tombstoned
- [ ] Operational `/healthz` and `/api/health` unchanged (no decision payload)

## Runtime verification

- [ ] Core starts in mock mode
- [ ] Core starts in live empty mode (valid unknown payloads)
- [ ] Docker Compose starts
- [ ] Reports generate and redact correctly (v3)
- [ ] MQTT Discovery **disabled** by default
- [ ] Topology **enabled** by default with startup scan only (no periodic refresh unless configured)
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
