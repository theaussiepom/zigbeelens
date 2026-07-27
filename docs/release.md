# Release process

How to cut a ZigbeeLens release. Use [RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md) as the gate.

## Versioning

ZigbeeLens uses [Semantic Versioning](https://semver.org/):

- **MAJOR** — breaking changes to config, API, or database migrations
- **MINOR** — new features, backwards-compatible
- **PATCH** — bug fixes, docs, CI

Pre-1.0 (`0.x.y`): minor bumps may include small breaking changes — document in CHANGELOG.

### Version sources

Align these on release:

| File | Field |
|------|-------|
| `apps/core/pyproject.toml` | `version` |
| `apps/core/src/zigbeelens/__init__.py` | `__version__` |
| `package.json`, `apps/ui/package.json`, `apps/core/package.json`, `packages/shared/package.json` | `version` |
| `apps/addon/zigbeelens/config.yaml` | `version` |
| `apps/ha_integration/.../manifest.json` | `version` |
| `deploy/docker/Dockerfile` | `ARG VERSION` default |
| `CHANGELOG.md` | release section |

Use `./scripts/bump-version.sh X.Y.Z` (which also updates the Dockerfile
metadata default), then run `./scripts/check-version-alignment.sh`.

## Release steps

### 1. Prepare branch

Ensure the release commit is based on current `main`. Confirm required remote CI
is green for that exact commit; local validation is separate evidence.

Before tagging, all release phases must be complete:

- Phase 7A query/cardinality/runtime baseline (merged in PR #100)
- Phase 7B test architecture and exact-v3 report reset (merged in PR #101)
- Phase 7C1 documentation truth (merged)
- Phase 7C2 screenshots (S1–S9 from the prior runtime are now stale; recapture
  all nine from one final corrected runtime)
- Phase 7D live Beast deployment validation (blocked)

The add-on is deferred and is not part of the current HACS release. Keep its
non-regression checks green, but do not publish or advertise it as a supported
route.

The correction closes production ownership gaps found by the release audit:
report controls and target failures, Discovery last-will validation order,
disabled-topology lifecycle, parsed topology persistence, mixed-case IEEE
lookups, investigation copy, artifact identity, and validation hardening.
Keep their behavioral gates in
[RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md); prose alone never closes a
runtime contract.

The HACS satellite is a separate publication gate. At the release-state
preflight, public `main` was commit
`21c24e3355369b94c9ab596cf9fc0591f1282297`, tree
`9e33bcbf919cdc90eee37e6c3f635f6b6292fbc9`, version `0.1.14`, with
`SOURCE_COMMIT` `906527063ad8bd594fbec51f69f6fc72205302dd`; no `v0.1.14`
tag or release exists. That is the prior candidate, not the corrected source,
so the public tree is stale again until a separately authorized
resynchronization. Use only a package generated from the final correction for
branch testing. Public installation remains gated, and this task does not
authorize satellite modification or publication.

The monorepo and generated stage now own durable HACS options, fail-closed
compatibility/repairs, exact enrichment lifecycle, declarative/runtime
single-entry behavior, exact HA `2025.1.0`/Python `3.12` and
`2026.7.3`/Python `3.14` lanes, and generated pinned official hassfest/HACS
jobs. Generated release publication depends on generated CI. Public install is
still unavailable until the satellite tree/version is synchronized and those
official jobs pass remotely on that exact tree.

The monorepo PR/main packaging gate and `v*` release gate also depend on the
dedicated `enrichment-live-e2e` job for the exact source commit. Generated HACS
CI is package-scoped and does not contain Core, the UI, or the live harness, so
its matrix and official checks complement rather than replace that monorepo
live-convergence result.

### 2. Update version

```bash
export ZIGBEELENS_RELEASE_VERSION=X.Y.Z
./scripts/bump-version.sh "$ZIGBEELENS_RELEASE_VERSION"
```

Replace `X.Y.Z` with the intended version. Do not reuse an existing tag.

### 3. Update CHANGELOG

Add release section to [CHANGELOG.md](../CHANGELOG.md).

### 4. Run full validation

```bash
bash scripts/validate-contracts.sh
./scripts/validate-docs.sh

cd apps/core
uv run pytest -q
uv run pytest -q tests/performance
uv run ruff check src tests
cd ../..

./scripts/smoke-sqlite-3.34.1.sh
pnpm --filter @zigbeelens/shared build
pnpm --filter @zigbeelens/ui test
pnpm --filter @zigbeelens/ui typecheck
pnpm --filter @zigbeelens/ui lint
pnpm --filter @zigbeelens/ui build
./scripts/validate-ha-integration.sh
./scripts/validate-addon.sh
ZIGBEELENS_REQUIRE_DOCKER_COMPOSE=1 ./scripts/validate-compose.sh
./scripts/package-hacs-repo.sh
./scripts/package-addon-repo.sh
./scripts/smoke-core.sh
./scripts/check-version-alignment.sh
git diff --check
```

`scripts/smoke-core.sh` is the canonical isolated Core runtime proof. It does
not activate or repair `apps/core/.venv`, invoke pip, read `config/config.yaml`,
or use repository `data/`. It resolves a verified checkout Python (explicit
`ZIGBEELENS_CORE_PYTHON`, then an isolated, lockless, non-project uv run that
installs the checkout as an editable dependency, then an already-usable
`python3`), creates a temporary config and SQLite database on a free loopback
port, disables collector, Discovery, and topology activity, verifies
schema/integrity and the public endpoints, and removes its exact child/state on
every exit path. The release helper resolves the same tracked Core inputs once
into a uv-managed environment under its temporary external state directory,
then uses that environment for Core lint, full tests, performance tests, and
its nested contract, safety, add-on, and smoke gates. It also retains the exact
minimum Home Assistant matrix environment inside the same temporary state and
reuses that already-proven Python for live E2E. Those gates do not create or
update `apps/core/uv.lock` or `apps/core/.venv`.

Record exact test counts, skips, xfails, and warnings. The model-pattern
Decision parity regression is strict and uses one explicit reference clock;
the full Core suite must have no unexplained xfail.

### 5. Build artifacts

```bash
./scripts/build-docker.sh
./scripts/build-addon.sh
./scripts/package-hacs-repo.sh
```

The generated HACS directory is a local stage, not a publication instruction.
Before public HACS guidance or publication is restored:

- the complete staged tree must match the intended satellite tree;
- the manifest/package version must uniquely identify that exact tree;
- exact Home Assistant 2025.1.0/Python 3.12 and
  2026.7.3/Python 3.14 lanes must pass;
- generated official HACS and hassfest validation must pass remotely on the
  synchronized satellite; and
- explicit publication authorization must be recorded before the external
  repository is modified.

The current schema target is `15`. Migration
`015_topology_raw_scrub.sql` removes unsafe legacy topology source dictionaries
while preserving normalized facts and the governed redacted capture.
Migration `014_report_v3_only_reset.sql` remains unchanged and continues to own
the one-time exact-v3 report reset.

Before any local or remote candidate is accepted, inspect its OCI metadata:

```text
org.opencontainers.image.version=0.1.14
org.opencontainers.image.revision=<full final source SHA>
org.opencontainers.image.source=https://github.com/theaussiepom/zigbeelens
```

Channel names (`edge`, `main`, `sha-*`, `latest`) are tags, never
package-version labels. GHCR manifest digest
`sha256:8549c49bd3e0389def669ce2e6c14bcbe2b54c967a725fd6373f5d82921f6bc7`
is rejected Phase 7D evidence because it reported OCI version `edge`; do not
reuse it.

### 6. Tag and push

```bash
git status --short
git add \
  package.json \
  apps/ui/package.json \
  apps/core/package.json \
  packages/shared/package.json \
  apps/core/pyproject.toml \
  apps/core/src/zigbeelens/__init__.py \
  apps/addon/zigbeelens/config.yaml \
  deploy/docker/Dockerfile \
  apps/ha_integration/custom_components/zigbeelens/manifest.json \
  CHANGELOG.md
git diff --cached --check
git diff --cached --stat
git commit -m "Release v${ZIGBEELENS_RELEASE_VERSION}"
git tag "v${ZIGBEELENS_RELEASE_VERSION}"
git push origin main
git push origin "v${ZIGBEELENS_RELEASE_VERSION}"
```

### 7. Publish Docker image

The [Docker workflow](../.github/workflows/docker.yml) builds on `v*` tags and
publishes the versioned image and `latest` tag to
`ghcr.io/theaussiepom/zigbeelens`.

### 8. GitHub release

Create a GitHub release from tag `v${ZIGBEELENS_RELEASE_VERSION}`:

- Title: `v${ZIGBEELENS_RELEASE_VERSION}`
- Body: CHANGELOG section
- Attach HACS zip if distributing manually

### 9. Add-on repository (deferred)

Do not include or publish the add-on in the current HACS release. Any future
add-on publication is a separate task gated by
[RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md).

### 10. Post-release verification

The current portable route is unconditional:

- [ ] Fresh released Docker install from [docker.md](docker.md)
- [ ] Generate a `public_safe` report
- [ ] Confirm MQTT Discovery off by default
- [ ] Confirm topology enabled with startup scan only (no periodic refresh by default)

Companion checks are conditional on the artifacts actually included in this
release:

- [ ] **If an add-on artifact was included and published after its package/live
  gates closed:** install that exact HAOS add-on artifact and verify Ingress.
- [ ] **If the HACS integration was synchronized and published after its
  tree/version/validation/authorization gates closed:** install that exact
  published HACS artifact and verify it against the released Docker Core.

## Review-thread closure before release

Use the exact inventory in
[RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md#review-thread-closure-inventory).
PR #106 discussions `discussion_r3654140180` and
`discussion_r3654140181`, PR #100 discussion `discussion_r3626646727`, PR #97
discussion `discussion_r3618354267`, and the delayed approved-host bypass
review remain unresolved until a future fixing PR is merged and an exact fixing
PR/commit reply is posted. Resolve only after that reply, then re-query each
source PR for non-outdated unresolved threads.

## Safety verification

Before every release:

```bash
./scripts/validate-safety-guardrails.sh
```

Review [safety-audit.md](safety-audit.md).

## Hotfix process

1. Branch from tag
2. Fix + test
3. Bump patch version
4. Tag the new patch version and publish

## Related

- [upgrades.md](upgrades.md)
- [backups.md](backups.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)
