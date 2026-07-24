# Release checklist

Use this checklist before tagging a release. See [docs/release.md](docs/release.md) for the full workflow.

## Automated tests and validation

Run the release helper, then close every explicit automated gate below. The
helper does not replace the Phase 7-specific checks or manual gates.

```bash
./scripts/run-release-checks.sh
```

- [ ] Backend tests pass (`cd apps/core && uv run pytest -q`)
- [ ] Ruff passes (`cd apps/core && uv run ruff check src tests`)
- [ ] Phase 7B contract lane passes (`bash scripts/validate-contracts.sh`)
- [ ] Phase 7A performance suite passes (`cd apps/core && uv run pytest -q tests/performance`)
- [ ] SQLite 3.34.1 runtime smoke passes (`./scripts/smoke-sqlite-3.34.1.sh`)
- [ ] Shared package build passes (`pnpm --filter @zigbeelens/shared build`)
- [ ] Shared package has no dedicated test suite; do not treat its no-op `test` script as release evidence
- [ ] UI tests pass (`pnpm --filter @zigbeelens/ui test`)
- [ ] UI lint passes (`pnpm --filter @zigbeelens/ui lint`)
- [ ] UI typecheck passes (`pnpm --filter @zigbeelens/ui typecheck`)
- [ ] UI production build passes (`pnpm --filter @zigbeelens/ui build`)
- [ ] Strict Compose validation renders all maintained configurations
      (`ZIGBEELENS_REQUIRE_DOCKER_COMPOSE=1 ./scripts/validate-compose.sh`);
      source-only non-strict output is partial evidence, not a release pass
- [ ] Hermetic Core smoke passes (`./scripts/smoke-core.sh`): it selects a
      verified checkout Python without pip, uses a free loopback port plus a
      temporary config/database, and leaves repository `config/` and `data/`
      untouched
- [ ] Version alignment check passes (`./scripts/check-version-alignment.sh`)
- [ ] Storage retention policy v2: telemetry / resolved incidents / reports; startup + periodic maintenance
- [ ] `zigbeelens storage check` / `backup` / `maintenance --dry-run` validated on a release candidate DB

### Structural companion-package validation

These checks validate source/package shape only. Passing them does **not**
establish publication readiness or replace the artifact-specific live gates
below.

- [ ] HA integration source validates (`./scripts/validate-ha-integration.sh`)
- [ ] Exact HA minimum lane passes
      (`bash scripts/test-ha-integration-matrix.sh minimum`:
      Home Assistant `2025.1.0`, Python `3.12`)
- [ ] Exact HA current lane passes
      (`bash scripts/test-ha-integration-matrix.sh current`:
      Home Assistant `2026.7.3`, Python `3.14`)
- [ ] Live enrichment convergence passes
      (`./scripts/test-enrichment-live-e2e.sh`: official HA registry →
      manager/client → Core SQLite/SSE/projection → mounted UI rename, area,
      and metadata-removal fallback on the exact minimum lane)
- [ ] The required monorepo PR/main `enrichment-live-e2e` check is green for
      the exact source commit, and the `v*` release gate depends on that same
      canonical live test rather than local-only evidence
- [ ] HACS staging package generates and validates (`./scripts/package-hacs-repo.sh` then `bash dist/zigbeelens-hacs/scripts/validate-hacs-repo.sh`)
- [ ] Generated HACS CI owns both exact HA lanes plus pinned official hassfest
      and HACS validation; generated release publication depends on that CI
- [ ] Add-on source structure validates (`./scripts/validate-addon.sh`)
- [ ] Add-on staging package generates and validates (`./scripts/package-addon-repo.sh` then `bash dist/zigbeelens-addons/scripts/validate-addon-repo.sh`)

The Core suite currently has one intentional non-strict xfail:
`test_incident_badge_matches_device_story_for_model_pattern` (`watch` versus
`informational` Decision-surface mismatch). Record it as **xfail**, not pass.
Any additional skip, xfail, or warning requires an explicit release note.

The canonical Core suite's SQLite 3.34.1 case is expected to skip outside its
dedicated container smoke and must still be recorded. The UI safety owner runs
against `apps/ui/src`; a missing production source directory is an assertion
failure, never a skip.

## Phase 7 release status

- [x] Phase 7A query/cardinality/runtime baseline merged (PR #100)
- [x] Phase 7B release-quality test architecture and exact-v3 report reset merged (PR #101)
- [x] Phase 7C1 documentation truth and cross-surface alignment merged
- [ ] Phase 7C2 current screenshots captured and reviewed
- [ ] Phase 7D live Beast deployment validation complete

Local validation evidence is not remote CI evidence. Do not mark Phase 7C2 or
Phase 7D complete from documentation or local tests.

The Home Assistant add-on is deferred and is not part of the current HACS
release. Its future-only gate remains below; structural validation is
non-regression evidence, not current installation readiness.

## Security acknowledgement

- [ ] I have set the intended `security.mode` (and know what this build actually enforces).
- [ ] I understand the process bind (`server.host`) — loopback vs non-loopback — and that status/Uvicorn share one AppConfig.
- [ ] I have decided whether to configure an API token (`ZIGBEELENS_SECURITY_API_TOKEN` / `_FILE` or legacy `ZIGBEELENS_API_KEY` config alias).
- [ ] If a token is set, I understand protected reads, mutations, SSE, and downloads require `Authorization: Bearer` (not `X-ZigbeeLens-Api-Key`).
- [ ] If I also set `session_secret`, I understand browser sessions use an HttpOnly cookie and cookie mutations need `X-ZigbeeLens-CSRF-Token`.
- [ ] I understand standalone Core in `local` mode without a token is trusted-open; the bundled UI uses session login when both token and session secret are set; HACS may store an optional Core API token for server-side bearer reads (never in panel/iframe URLs).
- [ ] I understand the image-based package generates add-on Ingress configuration, but its current entrypoint omits the source runner's optional token-file installation; token-enabled behavior is not verified.
- [ ] Standalone UI: trusted-open enters directly; existing session reloads; wrong token stays locked; correct token cookie round-trip unlocks; mutations send CSRF; SSE and report download use cookies; expiry/logout return to login; API token is absent from browser storage.
- [ ] I have checked logs/config status for accidental secret leakage.
- [ ] If Core is reachable beyond users/networks I trust, I have intentionally added a trusted proxy/firewall (or accepted the risk).
- [ ] I understand ZigbeeLens is read-only for Zigbee control and does not perform permit join, remove, reset, bind/unbind, OTA, or channel changes.
- [ ] I understand some API routes can modify ZigbeeLens local data, such as reports, topology snapshots, and Home Assistant enrichment metadata.
- [ ] I understand the HACS integration reads Core diagnostic/configuration/Decision/capability/inventory data and writes only the exact Core-local HA enrichment snapshot/explicit-removal clear; it does not publish MQTT.
- [ ] If using an FQDN/HTTPS route, I understand HTTPS is not authentication.
- [ ] If using a tablet/no-auth route, I have intentionally scoped it to trusted/local access or accepted the risk.

## Manual gates — real-world (Beast / production-like)

- [ ] Real GHCR edge container tested on Beast (`ghcr.io/theaussiepom/zigbeelens:edge`)
- [ ] Real MQTT broker tested with a dedicated `zigbeelens` user: subscribe permissions plus only the exact per-network `bridge/request/networkmap` publish needed by the default startup scan (and Discovery prefixes only when that optional feature is under test)
- [ ] Both real networks visible: `home`, `home2`
- [ ] Real report generation tested
- [ ] `public_safe` redaction tested with real data (password / network_key scrubbed)
- [ ] Docker logs secret-free

## HACS publication readiness and live gates

Required only when the HACS integration is included in the release. Structural
package validation above is necessary but not sufficient.

- [ ] The current branch is tested by manually installing
      `dist/zigbeelens-hacs/custom_components/zigbeelens` at
      `<home-assistant-config>/custom_components/zigbeelens`; the
      unsynchronized public satellite is not used as branch evidence
- [ ] The complete staged tree matches the intended
      `theaussiepom/zigbeelens-hacs` satellite tree exactly
- [x] The candidate manifest/package uses the previously unused version
      `0.1.14`, while the reviewed public satellite remains at `0.1.13`, so the
      manifest/package version uniquely identifies that tree
- [ ] Exact Home Assistant `2025.1.0` / Python `3.12` and Home Assistant
      `2026.7.3` / Python `3.14` both pass the same integration suite
- [ ] The canonical monorepo live enrichment E2E is green remotely for the
      exact source commit before satellite synchronization or tagging;
      generated satellite CI is package-scoped and does not replace this gate
- [ ] Synchronized HACS repository passes its structural validator plus the
      generated remote official HACS/hassfest checks
- [ ] Explicit authorization to synchronize and publish the HACS satellite is
      recorded before any external repository is modified
- [ ] Config flow accepts Core URL reachable from Home Assistant
- [ ] Single-entry ownership is declared in manifest metadata as well as enforced by config flow
- [ ] Native companion panel loads (cards, not raw JSON)
- [ ] **Open Full Dashboard** opens Core in a new tab (e.g. `http://192.168.100.5:8377`)
- [ ] Native companion summary is the default; Try Embedded View opts into iframe mode when browser mixed-content rules allow
- [ ] When HA is HTTPS and Core is HTTP, panel stays on native summary / blocked view (mixed content blocked)
- [ ] Back to Summary returns from embedded or blocked view to the native panel
- [ ] Reconfigure flow can change Core URL without delete/re-add; panel picks up new URL after reload
- [ ] Configure stores a 15–900-second polling interval durably; the selected value survives flow completion and one effective reload and changes the coordinator interval
- [ ] Missing or malformed Core versions project compatibility Unknown and cannot enable shared decisions
- [ ] Older, newer, and malformed Decision contracts plus malformed/missing exact-v2 Dashboard surfaces produce distinct truthful states/repairs
- [ ] HA registry name and area reach the correct exact network+IEEE Core/UI/report device while the Zigbee2MQTT friendly name remains available
- [ ] Duplicate IEEE across networks fails closed when original-source evidence cannot select exactly one Core row
- [ ] Accepted complete-empty enrichment clears; unavailable registry/inventory and transient POST failure retain the prior accepted snapshot
- [ ] Enrichment manager initial/event/retry/15-minute reconciliation has one owner and unload/reload does not duplicate listeners or clear accepted data
- [ ] Copy Core URL works
- [ ] HACS entities appear (overall decision, review-first, worth-reviewing, coverage warnings, active incident, device counts, per-network)
- [ ] Stop Core → panel shows calm disconnected state + Core unreachable repair
- [ ] Start Core → panel recovers and repair clears
- [ ] HACS diagnostics download is redacted (no secrets)
- [ ] Behind TLS reverse proxy: `cors_allowed_origins` includes the browser-visible `https://…` Core origin for sessions; `frame_ancestor_origins` lists HA separately when embedding

## Manual gates — mobile polish

- [ ] Core React UI pass at ~360–430px width (Overview, Mesh / Investigate, Devices, Incidents, Reports, Settings, Advanced menu)
- [ ] No horizontal page overflow on phone-sized viewport
- [ ] If HACS is included, its native companion panel passes on phone/tablet HA web/app
- [ ] If HACS is included, Open Full Dashboard is obvious on mobile

## Add-on publication readiness and live package gates (deferred)

Not part of the current HACS release. Preserve this checklist for a separate,
explicitly scoped future add-on task.

- [ ] Add-on repo validates (`./scripts/validate-addon.sh` + packaged repo check)
- [ ] No privileged mode, no host network, no Docker socket
- [ ] Ingress enabled; MQTT Discovery off; topology enabled for one startup scan with periodic/manual/incident capture gates off
- [ ] Packaged repository entrypoint matches the required add-on startup contract, including option conversion, exact Ingress security, `/data` writability, and optional token-file installation
- [ ] `security.api_token` from add-on options is installed/exported into Core; packaged HAOS bearer smoke passes
- [ ] Add-on `reporting.max_*` schema minimums match Core (`>= 1`); zero is rejected consistently
- [ ] `reporting.default_profile` is effective when a request omits a profile, or the ineffective option is removed and documentation is qualified
- [ ] Unused reporting options (`max_metric_samples_per_device`, `max_availability_changes_per_device`, `include_raw_payloads`) are implemented or removed
- [ ] A portable Home-Assistant-reachable Core origin for HACS is implemented and documented, or HACS interoperability is explicitly out of scope; do not assume `localhost` across namespaces while the add-on exposes `ports: {}`
- [ ] Packaged add-on with no API token: Ingress UI opens and SSE/download/mutation work
- [ ] Packaged add-on with optional token: Ingress still works and a direct bearer request succeeds
- [ ] Spoofed Ingress identity from a non-Supervisor peer fails
- [ ] Add-on README describes only behavior demonstrated by the packaged artifact
- [ ] HAOS manual install smoke test complete before add-on publication

## Decision contract / Track 5

- [ ] Capabilities advertise `decision_contract_version: 2` and `legacy_health_lens_payloads: false`
- [ ] Current Dashboard/Devices/Networks/Incidents payloads have no Lens/health presentation fields
- [ ] Saved reports are exact `report_version: 3`; non-v3 rows are not listed or downloaded
- [ ] HACS requires exact contract v2; incompatible Core shows repair (not reauth) and no health fallback
- [ ] HACS treats missing/malformed Core versions as compatibility Unknown and keeps shared decisions off
- [ ] HACS distinguishes unsupported decision contract from malformed/missing exact-v2 Dashboard surfaces and emits truthful repair guidance
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
- [ ] MQTT Discovery validates `{state_topic_prefix}/status` against Zigbee2MQTT base topics before registering the broker last will
- [ ] `topology.enabled: false` plus a positive refresh interval does not advertise an active scheduler that can only reject captures
- [ ] Parsed topology node/link `raw_json` storage has a reviewed scrub/retention contract
- [ ] SSE `/api/events/stream` works (not shadowed by static SPA catch-all)

## Safety

- [ ] Safety guardrail owner passes with zero skips (`./scripts/validate-safety-guardrails.sh`)
- [ ] Collector remains subscribe-only (default path)
- [ ] UI has no repair/reset/permit-join controls
- [ ] If HACS is included, its panel summary and diagnostics exclude secrets

## Documentation

- [ ] README updated
- [ ] CHANGELOG updated
- [ ] Version numbers aligned (see `./scripts/bump-version.sh`)
- [ ] Docs describe Docker + HACS native panel + add-on Ingress relationship
- [ ] README and product docs use the exact primary and Advanced & support navigation labels
- [ ] Configuration docs use implementation-derived option names and defaults
- [ ] Current report docs promise exact `ReportDetailV3` only; no v1/v2 reader/download path
- [ ] No docs promise iframe as normal HACS experience
- [ ] No docs imply reverse proxy required for HACS sidebar value
- [ ] Phase 7C2 screenshots show the current Decision-led UI and HACS contract-v2 companion

## Packaging and publish

- [ ] Docker image builds (`./scripts/build-docker.sh`)
- [ ] Release tag `v<version>` created only after the Docker/Core gates and all
      gates for companion artifacts included in this release pass
- [ ] Versioned Docker image pushed to GHCR (`ghcr.io/theaussiepom/zigbeelens:<version>`)
- [ ] If HACS is included after its publication gates close, the synchronized
      tree and uniquely identifying version are rechecked immediately before
      publication
- [ ] If HACS is included, its staged artifact is pushed to
      `theaussiepom/zigbeelens-hacs` only in the separately authorized
      publication task
- [ ] GitHub release notes published
- [ ] If an add-on is included, repository metadata is updated only after every
      generated-package publication blocker above is closed

## Post-release spot checks

- [ ] Fresh released Docker install from the stable docs quick start
- [ ] If HACS was included and published, install it from the published repo
- [ ] If an add-on was included and published, install that exact HAOS artifact
- [ ] Generate and download a `public_safe` report
- [ ] Confirm SSE works when Core is behind reverse proxy (optional advanced Docker path — see [docs/hacs-embedded-view.md](docs/hacs-embedded-view.md) for Caddy example)
