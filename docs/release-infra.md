# Release infrastructure inventory

Generated for three-repo release setup. GitHub owner: **theaussiepom** (from `gh auth status`).

## Current state (pre-changes)

| Item | Status |
|------|--------|
| Version | **0.1.0** across pyproject, manifest, add-on config |
| Git repo | Not initialized locally |
| Remote repos | None exist yet under `theaussiepom/` |
| Main CI | Single job — backend, UI, HA, add-on, smoke (passing locally) |
| Docker workflow | `IMAGE` TODO `ghcr.io/zigbeelens/zigbeelens`; push **only on v\* tags** |
| HACS packaging | `scripts/package-hacs.sh` → `dist/hacs/zigbeelens/` (nested, not repo-root layout) |
| Add-on source | `apps/addon/` with Dockerfile build-from-monorepo |
| Standalone Docker | `deploy/docker/Dockerfile` + `entrypoint.sh` (config mount only) |
| Local tests | Backend 156, UI 35, HA 30, validations pass |

## Target images

```
ghcr.io/theaussiepom/zigbeelens:edge      # main branch
ghcr.io/theaussiepom/zigbeelens:main      # alias
ghcr.io/theaussiepom/zigbeelens:sha-<sha> # traceability
ghcr.io/theaussiepom/zigbeelens:0.1.0     # release tag
ghcr.io/theaussiepom/zigbeelens:latest    # release tag only
```

## Target repos

| Repo | Purpose |
|------|---------|
| `theaussiepom/zigbeelens` | Monorepo source, CI, GHCR publish |
| `theaussiepom/zigbeelens-hacs` | HACS custom integration install |
| `theaussiepom/zigbeelens-addons` | HA add-on store repository |

## Changes in this pass

1. Split main CI into backend / ui / ha-integration / packaging / docker-build jobs
2. Fix Docker workflow — push `edge` on main, full tags on `v*`
3. Add `release-check.yml` for tag gates
4. Unify `entrypoint.sh` for HA options.json + standalone config (same GHCR image)
5. Add `scripts/package-hacs-repo.sh` and `scripts/package-addon-repo.sh`
6. Stage satellite repos under `dist/zigbeelens-hacs/` and `dist/zigbeelens-addons/`
7. Initialize git and create/push all three repos

## Local test (after main push + GHCR publish)

See [docs/release-test.md](release-test.md).
