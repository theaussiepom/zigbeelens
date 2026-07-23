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
- Phase 7C1 documentation truth
- Phase 7C2 current screenshots
- Phase 7D live Beast deployment validation

The add-on is a separate publication gate. Do not publish the packaged add-on
until its image entrypoint implements the complete add-on startup contract,
including optional `security.api_token` export and verified `/data`
writability; its `reporting.max_*` minimums align with Core;
`reporting.default_profile` is effective (or removed); and a portable
HACS-to-Core origin is defined.
`ports: {}` plus a separate Home Assistant namespace does not make
`localhost:8377` a portable HACS URL.

The documentation audit also found release gates outside add-on packaging:
unused report controls, unknown report targets producing an empty plan,
Discovery last-will validation order, disabled-topology scheduler/status
drift, parsed topology `raw_json` retention, and the HACS OptionsFlow
overwriting custom polling intervals with an empty options result. The HACS
compatibility helper also treats missing/malformed Core versions as compatible,
violating the documented Unknown tri-state and shared-decision gate, while
exact-v2 Dashboard payload-shape failure is misreported as an unsupported
contract requiring a Core upgrade. Track them in
[RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md); truthful documentation does
not close those runtime contracts.

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
./scripts/validate-compose.sh
./scripts/package-hacs-repo.sh
./scripts/package-addon-repo.sh
./scripts/smoke-core.sh
./scripts/check-version-alignment.sh
git diff --check
```

Record exact test counts, skips, xfails, and warnings. The known non-strict
xfail is
`test_incident_badge_matches_device_story_for_model_pattern` (`watch` versus
`informational` Decision-surface mismatch); it is not a pass.

### 5. Build artifacts

```bash
./scripts/build-docker.sh
./scripts/build-addon.sh
./scripts/package-hacs-repo.sh
```

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

### 9. Add-on repository

Update add-on repository metadata only after the add-on publication gates in
[RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md) pass against the packaged HAOS
artifact. Structural validation and a standalone `:edge` container are not
substitutes for that smoke test.

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
- [ ] **If the HACS integration was included and its publication gates
  closed:** install that exact packaged HACS artifact and verify it against the
  released Docker Core.

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
