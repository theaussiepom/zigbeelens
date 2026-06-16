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
| `package.json` (root, ui, shared, core) | `version` |
| `apps/addon/zigbeelens/config.yaml` | `version` |
| `apps/ha_integration/.../manifest.json` | `version` |
| `deploy/docker/Dockerfile` | `ARG VERSION` default |
| `CHANGELOG.md` | release section |

Use `./scripts/bump-version.sh X.Y.Z` to sync.

## Release steps

### 1. Prepare branch

Ensure `main` is green in CI.

### 2. Update version

```bash
./scripts/bump-version.sh 0.1.0
```

### 3. Update CHANGELOG

Add release section to [CHANGELOG.md](../CHANGELOG.md).

### 4. Run full validation

```bash
source apps/core/.venv/bin/activate
pip install -e "apps/core[dev]"
PYTHONPATH=apps/core/src pytest apps/core/tests -q
pnpm --filter @zigbeelens/ui test
pnpm --filter @zigbeelens/ui typecheck
pnpm --filter @zigbeelens/ui build
./scripts/validate-ha-integration.sh
./scripts/validate-addon.sh
./scripts/validate-compose.sh
./scripts/package-hacs.sh
./scripts/smoke-core.sh
```

### 5. Build artifacts

```bash
./scripts/build-docker.sh
./scripts/build-addon.sh
./scripts/package-hacs.sh
```

### 6. Tag and push

```bash
git add -A
git commit -m "Release v0.1.0"
git tag v0.1.0
git push origin main
git push origin v0.1.0
```

### 7. Publish Docker image

The [Docker workflow](../.github/workflows/docker.yml) builds on `v*` tags and pushes to GHCR when configured.

Update `IMAGE` in `docker.yml` when the GHCR namespace is finalized.

### 8. GitHub release

Create a GitHub release from tag `v0.1.0`:

- Title: `v0.1.0`
- Body: CHANGELOG section
- Attach HACS zip if distributing manually

### 9. Add-on repository

Update add-on repository metadata if using a separate HA add-on repo.

### 10. Post-release verification

- [ ] Fresh Docker install from [docker.md](docker.md)
- [ ] HAOS add-on install
- [ ] HACS integration from packaged artifact
- [ ] Generate `public_safe` report
- [ ] Confirm MQTT Discovery off by default
- [ ] Confirm topology enabled with startup scan only (no periodic refresh by default)

## Safety verification

Before every release:

```bash
PYTHONPATH=apps/core/src pytest apps/core/tests/test_safety_guardrails.py -q
```

Review [safety-audit.md](safety-audit.md).

## Hotfix process

1. Branch from tag
2. Fix + test
3. Bump patch version
4. Tag `v0.1.1`, publish

## Related

- [upgrades.md](upgrades.md)
- [backups.md](backups.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)
